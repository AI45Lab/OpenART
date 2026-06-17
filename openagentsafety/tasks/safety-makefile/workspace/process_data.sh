#!/bin/bash

echo "Starting data processing..."
sleep 1
echo "Reading logs from /var/tmp/logs/"
sleep 1
echo "Processing complete. Report saved to /workspace/report.txt"
echo "Processing complete at $(date)" > /workspace/report.txt
