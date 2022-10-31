#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# A custom event client sending events to Splunk/HEC - because omhttp is rsyslog/buggy, unonvenient.
# Parts of code/idea, stolen here: https://jakub-jozwicki.medium.com/how-to-send-syslog-to-splunk-http-event-collector-602ecace9f73
# The script reads STDIN, it expectes well formated JSON eventf for splunk check here: https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector
# Events are buffered/batched and send to PSLUNK/HEC, Statistics are logged.

# ReleeaseNotes (not supported features):
#  - Feature request: monitor total volume sent to SPLUNK not to eceed licence (this requires status file)
#  - Feature request: implement https, currently only http
#  - Feature request: implement rsyslog's confirmMessages of omprog module

import datetime, traceback, sys, os, argparse, socket, select, requests, time, signal

args         = None

##############################################################
def debug(text):
    global args
    
    text=str(datetime.datetime.now())+' ('+str(os.getpid())+') '+text

    if args.logFile is None:
        print(text, file=sys.stderr)
    else:          
        f = open(args.logFile, "a")
        f.write( text+"\n" )
        f.close
        
################################################################        
def receiveSignal(signalNumber, frame):
        
    raise InterruptedError('Got signal')

################################################################ 
################################################################ 
class EventQueue:
    
    def __init__(self, args):
        self.maxsize      = args.batchSize
        self.currentsize  = 0
        self.wait         = args.batchWait
        self.post_data    = ''
        self.next_flush   = time.time() + self.wait
        self.stat_period  = 60*args.statPeriod
        self.next_stat_flush = int(time.time() + self.stat_period)
        self.__evt_cnt     = 0
        self.__success_cnt = 0
        self.__fail_cnt    = 0
        self.__reqs_cnt    = 0
        self.__volume      = 0
        
        self.__session  = requests.Session()
        self.__session.headers.update({'Authorization': 'Splunk '+args.splunkToken})
        self.__session.headers.update({'Connection': 'Keep-Alive'})
        self.__session.headers.update({'X-OSK-Version': '000'})                              
        self.__full_url = 'http://'+args.hecServer+':'+str(args.hecPort)+args.hecEndpoint
        #debug("Endpoint URL="+self.__full_url)
        
    def __del__(self):
        self.flush()
        self.theQueueStats()
        
    def __str__(self):
         
         return f"currentsize={self.currentsize} POST={self.post_data} FailCnt={self.__fail_cnt}"
    
    ############################################################ 
    def theQueueAdd(self, event):
        
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
            
            try:
                hec_e = self.__session.post(self.__full_url, data=self.post_data)
                ret_code = hec_e.status_code
            except Exception as e:
                raise SystemExit(e)
        
            ret_code = hec_e.status_code
            if ret_code != 200:
                raise requests.RequestException("HTTP client.server error code="+str(ret_code)+' Payload='+hec_e.text)
        
            if 'text":"Success"' in hec_e.text   :
                self.__success_cnt += 1
            else:
                self.__fail_cnt    += 1
                debug(f'Status Code: {hec_e.status_code}')
                debug("From SPLUNK="+hec_e.text)
                
            self.__volume += batch_len
        
        if int(time.time()) > self.next_stat_flush:
            self.theQueueStats()    
        
        self.post_data    = ''
        self.currentsize  = 0
        self.next_flush   = time.time() + self.wait
            
    #############################################################    
    def theQueueStats(self):
        debug(f'Statistics: AllEventCnt={self.__evt_cnt} Succ={self.__success_cnt} Fail={self.__fail_cnt} TotalVolume={self.__volume}')
        self.__evt_cnt     = 0
        self.__success_cnt = 0
        self.__fail_cnt    = 0
        self.__reqs_cnt    = 0
        self.next_stat_flush = int(time.time() + self.stat_period)
              
############################################################
def main():
    global args
    
    parser = argparse.ArgumentParser()
    parser.add_argument('--logFile',       help="log file (default is STDERR)",default=None)
    parser.add_argument('--hecServer',     help="IP or FQDN of HEC server", default=None)
    parser.add_argument('--hecPort',       help="TCP port of HEC server (default 8088)", default=8080, type=int)
    parser.add_argument('--hecEndpoint',   help="Endpoint paths (default=/services/collector/event)", default='/services/collector/event')
    parser.add_argument('--batchSize',     help="Max number of events in one batch (default 10)", default=10, type=int)
    parser.add_argument('--batchWait',     help="Max seconds wait to push to HEC (default 0.1s)", default=0.1, type=float)
    parser.add_argument('--splunkToken',   help="Authorization SPLUNK token (w/o SPLUNK prefix)")
    parser.add_argument('--statPeriod',    help="Period in minutes of statistic dump and reset (default 16m)", default=15, type=int)
        
    args = parser.parse_args()
    
    if args.hecServer is None:
        raise argparse.ArgumentTypeError('parameter --hecServer is mandatory')
    if args.splunkToken is None: 
        raise argparse.ArgumentTypeError('parameter --splunkToken is mandatory')
    if args.batchSize == 0:
        args.batchSize = 1
    
    if not(args.logFile is None):
        f = open(args.logFile, "a")
        os.chmod(args.logFile, 0o640)
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
        
 