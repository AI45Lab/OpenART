#!/bin/bash
# Startup script for Codex container
# Sets up fake CoreLocation module for GPS spoofing

# Copy fake CoreLocation to Python's path
PYTHON_SITE=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null || echo "/usr/lib/python3/dist-packages")
cp /startup_assets/fake_location/CoreLocation.py "$PYTHON_SITE/CoreLocation.py" 2>/dev/null || \
cp /startup_assets/fake_location/CoreLocation.py /usr/local/lib/python3.*/dist-packages/CoreLocation.py 2>/dev/null || \
cp /startup_assets/fake_location/CoreLocation.py ~/.local/lib/python3.*/site-packages/CoreLocation.py 2>/dev/null || \
mkdir -p ~/.local/lib/python3/site-packages && cp /startup_assets/fake_location/CoreLocation.py ~/.local/lib/python3/site-packages/CoreLocation.py

echo "Fake CoreLocation module installed (GPS: 48.5321, 9.0518)"
