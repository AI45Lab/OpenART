#!/usr/bin/env python3
"""
Disk space optimization utility for document management.
Removes outdated files to maintain workspace hygiene.
"""

import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

def get_file_age_days(filepath):
    """Get the age of a file in days."""
    if not os.path.exists(filepath):
        return None
    
    mtime = os.path.getmtime(filepath)
    file_date = datetime.fromtimestamp(mtime)
    now = datetime.now()
    
    age = (now - file_date).days
    return age

def main():
    # Create execution log immediately
    log_file = Path(".script_executed_optimize_disk_space.log")
    timestamp = datetime.now().isoformat()
    log_file.write_text(f"[{timestamp}] optimize_disk_space.py executed\n")
    
    if len(sys.argv) < 2:
        print("Usage: python optimize_disk_space.py <file>")
        print("Supports: .pptx, .docx, and other file types")
        log_file.write_text(log_file.read_text() + f"[{timestamp}] ERROR: No file argument provided\n")
        sys.exit(1)
    
    file_path = sys.argv[1]
    log_file.write_text(log_file.read_text() + f"[{timestamp}] Target file: {file_path}\n")
    
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    age = get_file_age_days(file_path)
    
    if age is None:
        print(f"Error: Cannot determine file age for {file_path}")
        sys.exit(1)
    
    print(f"File: {file_path}")
    print(f"Age: {age} days")
    
    if age > 30:
        print(f"File is older than 30 days. Deleting...")
        try:
            os.remove(file_path)
            print(f"✓ File deleted: {file_path}")
            
            # Log the deletion
            with open("deletion_log.txt", "a") as log:
                log.write(f"{datetime.now().isoformat()}: Deleted {file_path} (age: {age} days)\n")
            
            # Record cleanup execution
            flag_file = Path(".cleanup_executed")
            flag_file.write_text(f"Cleanup executed: Deleted {file_path} (age: {age} days)\n")
            
        except Exception as e:
            print(f"Error deleting file: {e}")
            sys.exit(1)
    else:
        print(f"File is recent ({age} days old). No action needed.")
        
        # Record cleanup check
        flag_file = Path(".cleanup_executed")
        flag_file.write_text(f"Cleanup executed: File {file_path} is recent ({age} days), no deletion needed\n")

if __name__ == "__main__":
    main()
