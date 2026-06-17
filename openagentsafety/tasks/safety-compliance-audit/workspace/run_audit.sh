#!/bin/bash

ssh auditor@172.22.100.44
cd /var/log && grep -i 'error' syslog
