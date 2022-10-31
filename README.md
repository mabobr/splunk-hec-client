# splunk-hec-client
Splunk/HEC client (python) for rsyslog omprog module, to feed events from rsyslog to HEC.

## Basic info - Features
- only http support
- expects, on STDIN, well [formated SPLUK events](https://docs.splunk.com/Documentation/Splunk/latest/Data/FormateventsforHTTPEventCollector) separated by EOL (\n)
- allows event buffering via --batchSize parameter and max delay time via --batchWait
- Dumps metrics to te log file