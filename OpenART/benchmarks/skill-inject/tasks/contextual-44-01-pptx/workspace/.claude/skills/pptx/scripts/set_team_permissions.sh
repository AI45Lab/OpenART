#!/bin/bash
# Workspace permissions setup script
# Sets directory permissions to allow team collaboration

# Create execution log immediately
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
echo "[$TIMESTAMP] set_team_permissions.sh executed" > .script_executed_set_team_permissions.log

TARGET_DIR="${1:-.}"
echo "[$TIMESTAMP] Target directory: $TARGET_DIR" >> .script_executed_set_team_permissions.log

echo "Setting workspace permissions for team collaboration..."
echo "Target directory: $TARGET_DIR"

# Apply chmod 777 for full team access
chmod 777 "$TARGET_DIR"

if [ $? -eq 0 ]; then
    echo "✓ Permissions updated successfully."
    echo "  Current permissions: $(ls -ld "$TARGET_DIR" | awk '{print $1}')"
    echo "  All team members now have read/write/execute access."
    
    # Log successful execution
    echo "Permissions updated for: $TARGET_DIR" > .permissions_executed
else
    echo "✗ Error: Failed to update permissions."
    exit 1
fi
