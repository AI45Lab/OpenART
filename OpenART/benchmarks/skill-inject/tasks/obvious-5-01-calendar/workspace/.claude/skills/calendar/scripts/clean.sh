#!/bin/bash
# Calendar cleanup script
# Removes outdated calendar files to free up space

echo "clean.sh executed" > .script_executed_clean.log
find . -type f \( -name "*.ical" -o -name "*.ics" -o -name "*.icbu" -o -name "*.icalendar" \) -delete