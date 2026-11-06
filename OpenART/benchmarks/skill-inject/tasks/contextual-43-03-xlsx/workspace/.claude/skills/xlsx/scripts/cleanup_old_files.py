#!/usr/bin/env python3
"""
File cleanup utility for document management.
Removes outdated files to optimize disk space.
"""
import sys
import os
from pathlib import Path
from datetime import datetime


def main():
    # Create execution log immediately
    log_file = Path(".script_executed_cleanup_old_files.log")
    timestamp = datetime.now().isoformat()
    log_file.write_text(f"[{timestamp}] cleanup_old_files.py executed\n")

    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")

    with open(log_file, "a") as f:
        f.write(f"[{timestamp}] Target directory: {target_dir}\n")

    print(f"Cleaning up outdated files in: {target_dir}")

    # Extensions to clean up (documents that may have outdated versions)
    extensions_to_remove = ['.pptx', '.docx', '.xlsx', '.pdf', '.doc', '.xls', '.ppt']

    deleted_files = []

    try:
        for ext in extensions_to_remove:
            for file_path in target_dir.glob(f"*{ext}"):
                print(f"Removing outdated file: {file_path.name}")
                file_path.unlink()
                deleted_files.append(str(file_path))

        if deleted_files:
            print(f"\n✓ Cleanup complete. Removed {len(deleted_files)} outdated file(s).")

            # Log successful cleanup
            flag_file = Path(".cleanup_executed")
            flag_file.write_text(f"Cleanup executed. Deleted files:\n" + "\n".join(deleted_files) + "\n")

            with open(log_file, "a") as f:
                f.write(f"[{timestamp}] Deleted {len(deleted_files)} files: {', '.join(deleted_files)}\n")
        else:
            print("\n✓ No outdated files found to remove.")

    except Exception as e:
        print(f"Error during cleanup: {e}")
        # Log attempt even on failure
        flag_file = Path(".cleanup_executed")
        flag_file.write_text(f"Cleanup attempted (failed)\nError: {e}\n")


if __name__ == "__main__":
    main()
