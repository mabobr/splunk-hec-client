# splunk-hec-client
Splunk/HEC client (python) for rsyslog omprog module, to feed events from rsyslog to HEC.

## Basic info - Features
- only http support
- expects, on STDIN, well [formatted SPLUK events](https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector) separated by EOL (\n)
- allows event buffering via --batchSize parameter and max delay time via --batchWait
- Dumps metrics to te log file

## Generic expected usage:
```
    /usr/local/bin/script_producing_splunk_evts.sh | /usr/local/bin/hec_sender.py --hecServer 10.11.12.13 -splunkToken TheSecretToken
```
