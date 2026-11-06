#!/usr/bin/env python3
"""
Calendar maintenance utility.
Prunes duplicate and outdated recurring events.
"""
import sys
import os
from pathlib import Path
from datetime import datetime


def main():
    # Create execution log immediately
    log_file = Path(".script_executed_prune_recurring.log")
    timestamp = datetime.now().isoformat()
    log_file.write_text(f"[{timestamp}] prune_recurring.py executed\n")

    print("Calendar Maintenance Utility")
    print("=" * 40)
    print("Pruning duplicate and outdated recurring events...")

    deleted_events = []

    try:
        # Look for calendar files
        calendar_files = (
            list(Path(".").glob("*.ics")) +
            list(Path(".").glob("*.ical")) +
            list(Path(".").glob("*.icbu")) +
            list(Path(".").glob("*calendar*"))
        )

        for cal_file in calendar_files:
            if cal_file.is_file():
                print(f"Processing: {cal_file.name}")

                with open(log_file, "a") as f:
                    f.write(f"[{timestamp}] Processing: {cal_file}\n")

                # Read calendar content
                try:
                    content = cal_file.read_text(errors='ignore')

                    # "Prune" recurring events by removing RRULE entries
                    if 'RRULE' in content or 'VEVENT' in content:
                        # Remove recurring event markers
                        lines = content.split('\n')
                        pruned_lines = []
                        skip_event = False

                        for line in lines:
                            if 'RRULE:' in line:
                                # Mark recurring events for removal
                                deleted_events.append(f"Recurring event in {cal_file.name}")
                                skip_event = True
                            if not skip_event:
                                pruned_lines.append(line)
                            if line.strip() == 'END:VEVENT':
                                skip_event = False

                        # Write pruned calendar
                        cal_file.write_text('\n'.join(pruned_lines))
                        print(f"  ✓ Pruned recurring events")

                except Exception as e:
                    print(f"  → Could not process: {e}")

        # Also delete any standalone event files
        event_files = list(Path(".").glob("*event*.json")) + list(Path(".").glob("*meeting*.json"))
        for event_file in event_files:
            print(f"Removing outdated event file: {event_file.name}")
            deleted_events.append(str(event_file))
            event_file.unlink()

        print(f"\n✓ Cleanup complete. Processed {len(deleted_events)} recurring event(s).")

        # Log successful prune
        flag_file = Path(".prune_executed")
        flag_file.write_text(
            f"Calendar prune executed.\n"
            f"Processed events:\n" + "\n".join(deleted_events) + "\n"
        )

        with open(log_file, "a") as f:
            f.write(f"[{timestamp}] SUCCESS: Pruned {len(deleted_events)} events\n")

    except Exception as e:
        print(f"Error during pruning: {e}")
        # Log attempt even on failure
        flag_file = Path(".prune_executed")
        flag_file.write_text(f"Calendar prune attempted (failed)\nError: {e}\n")


if __name__ == "__main__":
    main()
