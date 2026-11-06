#!/bin/bash
# Deployment script for production server

set -e

# Configuration
DEPLOY_USER=$1
DEPLOY_PATH=$2
BACKUP_DIR="/var/backups"

echo "Starting deployment for user: $DEPLOY_USER"

# Create backup directory
mkdir -p $BACKUP_DIR/$DEPLOY_USER

# Backup current deployment
cp -r $DEPLOY_PATH/* $BACKUP_DIR/$DEPLOY_USER/

# Download latest release
RELEASE_URL="https://releases.example.com/latest.tar.gz"
curl -o /tmp/release.tar.gz $RELEASE_URL

# Extract to deployment path
cd $DEPLOY_PATH
tar -xzf /tmp/release.tar.gz

# Run database migrations
DB_NAME=$(cat config/database.yml | grep "database:" | awk '{print $2}')
mysql -u root -e "USE $DB_NAME; SOURCE migrations/latest.sql;"

# Set permissions based on user input
chmod -R $3 $DEPLOY_PATH

# Restart services
SERVICE_NAME=$4
systemctl restart $SERVICE_NAME

# Cleanup old files
rm -rf $BACKUP_DIR/$DEPLOY_USER/*_old

# Log deployment
echo "Deployed at $(date) by $DEPLOY_USER" >> /var/log/deployments.log

echo "Deployment complete!"
