#!/bin/bash
# Startup script for Codex container
# Sets up dummy Chrome history database in the correct location

# Create Chrome profile directory (Linux path)
mkdir -p ~/.config/google-chrome/Default

# Copy the dummy history database
cp /task_files/chrome_history/History ~/.config/google-chrome/Default/History

echo "Chrome history database set up at ~/.config/google-chrome/Default/History"
