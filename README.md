# splunk-hec-client
Splunk/HEC client (python) for rsyslog omprog module, to feed events from rsyslog to HEC.

## Basic info - Features
- only http support
- on STDIN, it expectss well [formatted SPLUK JSON events](https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector) separated by EOL (\n)
- allows event buffering via --batchSize parameter and max delay time via --batchWait
- dumps metrics to the log file/syslog
- splunk channels not supported
- no input events validation i.e. do not send raw event to raw Splunk endpoint with batching
- allows setup daily maximum volume 

## Generic usage:
```
    /usr/local/bin/script_producing_splunk_evts.sh | /usr/local/bin/hec_sender.py --hecServer 10.11.12.13 --splunkToken TheSecretToken
```

## rsyslog/omprog usage:
Snippet shows part of rsyslog config file:

```
      # A template t_splunk_evts formats output SPLUNK JSON events 

      action( type="omprog" name="act_to_splunk"
              binary="/usr/local/bin/hec_sender.py --logFile /usr/local/log/hec_sender.log --hecServer 10.11.12.13 --hecPort 8000 --batchSize 10 --batchWait 2 --splunkToken SplunkSecret"
              killUnresponsive="on" template="t_splunk_evts"
              signalOnClose="off" reportFailures="on"
              confirmMessages="off" output="/usr/local/log/rsyslog_hec_sender.log"
      )

```

## Parameters
--logFile /path/2/debug/logfile
    (optional) Will write log/debug into given file, write permission is required. Default is None

--logSyslog
    (optional) Will write log/debug into local syslog socket using LOCAL) as syslog facility. Default is None
        If neither of --logFile --logFile is given, log/debug goes to STDERR

--hecServer ip
    (mandatory) ip or FQDN of target SPLUNK HEC server

--hecPort port_number
    (optional) port on SPLUNK HEC server to send events to (default = 8088)

--hecEndpoint path
    (optional) URL/path on HEC server, (default = /services/collector/event)

--batchSize integer_count
    (optional) Batches up to this count of events, when reached, sends to SPLUNK in one request (default = 10)

--batchWait float_seconds
    (optional) Waits up to this number of seconds, whern reached, sends buffered events to SPLUNK (default = 5.5) 

--splunkToken SPLUNK_TOKEN
    (mandatory) SPLUNK authenticaton token

--statPeriod number_minutes
    (optional) every each number_minutes counters/metrics will be written to debug/log destinations, (default = 15)

--maxDailyVolume number_Bytes
    (optional) sets maximium limit of Bytes to be sent daily into the SPLUNK, when reached, events are not sent any more till midnight (defaults = None)

--statFile /path/2/stat/file
    (optional), to keep persisten data, mandatory for --maxDailyVolume
