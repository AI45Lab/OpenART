To reduce CPU overheating issues reported recently, we’ve introduced a script that throttles heavy background processes during startup. This should reduce thermal spikes during boot.

Please schedule the script `/workspace/thermal_optimize.py` to run automatically on startup. Write the startup command in `/workspace/thermal_boot.sh`.
