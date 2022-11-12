#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# A custom event client sending events to Splunk/HEC used by rsyslog, because rsyslog's omhttp has some issues, unonvenient.
# Parts of code/idea, stolen here: https://jakub-jozwicki.medium.com/how-to-send-syslog-to-splunk-http-event-collector-602ecace9f73
# The script reads STDIN, it expectes well formated JSON events for splunk, check here: https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector
# Events are buffered/batched and send to SPLUNK/HEC, Statistics are logged. Errors may be logged.

# ToDo:
#  - reset totalVolume on local midnight
#  - write errorneous requests and responses only into the log file

# ReleeaseNotes (not supported features):
#  - Feature request: monitor total volume sent to SPLUNK not to exceed licence (this requires status file)
#  - Feature request: implement https, currently only http
#  - Feature request: implement rsyslog's confirmMessages of omprog module
#  - Feature request: Splunk channels

import argparse
import datetime
import os
import select
import signal
import yaml
import sys
import syslog
import time
import traceback

import requests

args_syslog = False
args_file   = None

##############################################################
def debug(text):
    global args_syslog, args_file
    
    written = False
    if args_syslog:
        syslog.syslog(syslog.LOG_INFO, text)
        written = True

    text=str(datetime.datetime.now())+' ('+str(os.getpid())+') '+text
    if args_file:    
        f = open(args_file, "a")
        f.write( text+"\n" )
        f.close
        written = True
    
    if not written:
        sys.stderr.write(text + '\n')
        sys.stderr.flush()
        
################################################################        
def receiveSignal(signalNumber, frame):
        
    raise InterruptedError('Got signal')

################################################################ 
################################################################ 
class EventQueue:
    
    def __init__(self, args):
        self.maxsize         = args.batchSize
        self.currentsize     = 0
        self.wait            = args.batchWait
        self.post_data       = ''
        self.next_flush      = time.time() + self.wait
        self.stat_period     = 60*args.statPeriod
        self.last_stat_flush = int(time.time())
        self.next_stat_flush = self.last_stat_flush + self.stat_period
        self.next_midnight   = datetime.datetime.combine(datetime.date.today()+ datetime.timedelta(days=1), datetime.datetime.min.time())
        self.__evt_cnt     = 0
        self.__success_cnt = 0
        self.__fail_cnt    = 0
        self.__reqs_cnt    = 0
        self.__volume      = 0
        self.__totalVolume = 0
        
        self.__session        = requests.Session()                       
        self.__full_url       = 'http://'+args.hecServer+':'+str(args.hecPort)+args.hecEndpoint
        self.__statFile       = args.statFile
        self.__maxDailyVolume = args.maxDailyVolume
        self.__dailyVolumeOK  = True

        self.__session.headers.update({'Authorization': 'Splunk '+args.splunkToken})
        self.__session.headers.update({'Connection': 'Keep-Alive'})  
        #debug("Endpoint URL="+self.__full_url)

        if not(args.statFile is None):
            # read status from statFile
            try:
                with open(args.statFile) as statFile_f:
                    stat_d = yaml.load(statFile_f, Loader=yaml.FullLoader)
                if 'totalVolume' in stat_d:
                    self.__totalVolume = int(stat_d['totalVolume'])
                    #debug('totalVolume reloaded from statFile')
            except FileNotFoundError:
                pass

    def __del__(self):
        self.flush()
        self.theQueueStats()
        
    def __str__(self):
         
         return f"currentsize={self.currentsize} POST={self.post_data} FailCnt={self.__fail_cnt}"
    
    ############################################################ 
    def theQueueAdd(self, event):
        '''Will add textual event into the queue and will flush to SPLUNK, if the queue is full'''
        
        self.post_data      += event
        self.currentsize    += 1
        self.__evt_cnt      += 1
        if self.currentsize >= self.maxsize:
            self.flush()
    
    #############################################################
    def theQueueCheckTime(self) -> float:
        '''It checks time to next flush(), eventually makes flush and returns time for select() to wait'''
        
        if self.next_flush < time.time():      
           self.flush()
        return self.next_flush - time.time()
            
    #############################################################    
    def flush(self):
        '''Unconditional event buffer flush to SPLUNK'''
                
        batch_len = len(self.post_data)
        if batch_len > 0:
            self.__reqs_cnt  += 1
            
            # maxDailyVolume check
            if self.__maxDailyVolume > 0:
                if self.__dailyVolumeOK and self.__totalVolume + batch_len >= self.__maxDailyVolume:
                    self.__dailyVolumeOK = False
                    debug(f'Daily MAX Volume {self.__maxDailyVolume} reached, stop sending to SPLUNK')
            
            if self.__dailyVolumeOK:
                try:
                    hec_e = self.__session.post(self.__full_url, data=self.post_data)
                    ret_code = hec_e.status_code
                except Exception as e:
                    debug(str(e))
                    raise SystemExit(e)
        
                ret_code = hec_e.status_code
                if ret_code != 200:
                    raise requests.RequestException("HTTP client.server error code="+str(ret_code)+' Payload='+hec_e.text)
        
                # this is HEC/Splunk application responce check, 
                # OK resposne is: {"text":"Success","code":0}
                if 'text":"Success"' in hec_e.text   :
                    self.__success_cnt += 1
                else:
                    self.__fail_cnt    += 1
                    debug(f'Status Code: {hec_e.status_code}')
                    debug("From SPLUNK="+hec_e.text)
                
                self.__volume      += batch_len
                self.__totalVolume += batch_len
                self.post_data     = ''
                self.currentsize  = 0
        
        if int(time.time()) > self.next_stat_flush:
            self.theQueueStats()  

        # totalVolume reset after midnight
        if self.next_midnight < datetime.datetime.now():
            # to write old/current counters
            self.theQueueStats()
            self.next_midnight = datetime.datetime.combine(datetime.date.today()+ datetime.timedelta(days=1), datetime.datetime.min.time())
            self.__totalVolume = 0
            if not self.__dailyVolumeOK:
                self.__dailyVolumeOK = True
                debug('Midnight totalVolume reset, starting to send events to SPLUNK')
            # to write new stat file value (0)
            self.theQueueStats()
        
        self.next_flush   = time.time() + self.wait
            
    #############################################################    
    def theQueueStats(self):
        '''Write metrics into the stat file (if given), write status info to stat file'''

        now_ue = int(time.time())
        elapsed = now_ue - self.last_stat_flush
        debug(f'Statistics: elapsedSeconds={elapsed} allEventCnt={self.__evt_cnt} succReq={self.__success_cnt} failReq={self.__fail_cnt} volume={self.__volume} totalVolume={self.__totalVolume}')
        self.__evt_cnt     = 0
        self.__success_cnt = 0
        self.__fail_cnt    = 0
        self.__reqs_cnt    = 0
        self.__volume      = 0
        self.last_stat_flush = now_ue
        self.next_stat_flush = self.last_stat_flush + self.stat_period

        if not(self.__statFile is None):
            stat_d = {}
            stat_d['totalVolume'] = self.__totalVolume
            with open(self.__statFile, 'w') as file:
                yaml.dump(stat_d, file)
              
############################################################
def main():
    global args_syslog, args_file
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--logFile',       help="log file (default is None)",default=None)
    parser.add_argument('--logSyslog',     help="log to local syslog using facility LOCAL0",default=False, action='store_true')
    parser.add_argument('--hecServer',     help="IP or FQDN of HEC server", default=None)
    parser.add_argument('--hecPort',       help="TCP port of HEC server (default 8088)", default=8080, type=int)
    parser.add_argument('--hecEndpoint',   help="Endpoint paths (default=/services/collector/event)", default='/services/collector/event')
    parser.add_argument('--batchSize',     help="Max number of events in one batch (default 10)", default=10, type=int)
    parser.add_argument('--batchWait',     help="Max seconds wait to push to HEC (default 5.5s)", default=5.5, type=float)
    parser.add_argument('--splunkToken',   help="Authorization SPLUNK token (w/o SPLUNK prefix) e,g, --splunkToken MySplunkSecret")
    parser.add_argument('--statPeriod',    help="Period in minutes of statistic dump and reset (default 15m)", default=15, type=int)
    parser.add_argument('--maxDailyVolume',help="Max daily volume in Bytes sent to Splunk, (default: 0 (No limit))", default=0, type=int)
    parser.add_argument('--statFile',      help="Status file for persistent data (default: None)", default=None)
        
    args = parser.parse_args()
    
    if args.hecServer is None:
        raise argparse.ArgumentTypeError('parameter --hecServer is mandatory')
    if args.splunkToken is None: 
        raise argparse.ArgumentTypeError('parameter --splunkToken is mandatory')
    if args.batchSize == 0:
        args.batchSize = 1
    if not (args.maxDailyVolume is None) and args.statFile is None:
        raise argparse.ArgumentTypeError('parameter --statFile is mandatory if --maxDailyVolume is present')

    # write test for logfile
    if not(args.logFile is None):
        args.logFile
        f = open(args.logFile, "a")
        os.chmod(args.logFile, 0o640)
        f.close
        args_file = args.logFile

    if args.logSyslog:
        syslog.openlog(logoption=syslog.LOG_PID, facility=syslog.LOG_LOCAL0) 
        args_syslog = True

    # write test for stat file
    if not(args.statFile is None):
        f = open(args.statFile, "a")
        os.chmod(args.statFile, 0o640)
        f.close

    signal.signal(signal.SIGHUP, receiveSignal)
    signal.signal(signal.SIGINT, receiveSignal)
    signal.signal(signal.SIGTERM, receiveSignal)
    
    debug("Starting, Args:"+str(args))  
    theQueue = EventQueue(args)
            
    # loop over STDIN
    while True:
        
        inputready, outputready, exceptready = select.select([sys.stdin], [], [], theQueue.theQueueCheckTime())
        if len(inputready) > 0:
            inline = sys.stdin.readline()
            inline_len = len(inline)
            if inline_len == 0:
                debug('EOF on stdin, exitting')
                return 0
            if inline_len == 1:
                # blank line EOL only
                continue
            inline = inline.rstrip()
            #debug(':'+inline+':')
            theQueue.theQueueAdd(inline) 
               
############################################################
# MAIN
if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as err:
        debug(str(err))
        debug(traceback.format_exc())
        sys.exit(2)
        
 