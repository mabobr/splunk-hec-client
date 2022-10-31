# splunk-hec-client
Splunk/HEC client (python) for rsyslog omprog module, to feed events from rsyslog to HEC.

## Basic info - Features
- only http support
- expects, on STDIN, well [formatted SPLUK events](https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector) separated by EOL (\n)
- allows event buffering via --batchSize parameter and max delay time via --batchWait
- Dumps metrics to te log file

## Generic expected usage:
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
              confirmMessages="off" output="/storage/app/rsyslog/var/logs/rsyslog_hec_sender.log"
      )

```
