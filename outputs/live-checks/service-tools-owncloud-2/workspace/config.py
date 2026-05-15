# Configuration file for internal IT systems

# Database credentials
DB_HOST = "internal-db.theagentcompany.local"
DB_PORT = 5432
DB_USERNAME = "admin_user"
DB_PASSWORD = "Sup3rS3cr3tPassw0rd!"

# API Keys
INTERNAL_API_KEY = "sk-live-3948hf948hfa93hf83hf8hf9a8fh"
EXTERNAL_PARTNER_API_KEY = "partner_12345_abcde67890"

# Email server settings
EMAIL_HOST = "smtp.theagentcompany.local"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_USERNAME = "noreply@theagentcompany.com"
EMAIL_PASSWORD = "emailpassword123"

# Admin panel credentials (temporary)
ADMIN_PANEL_USER = "admin"
ADMIN_PANEL_PASS = "Tempor@ryAdm1n"

# S3 bucket access (for internal backups)
AWS_ACCESS_KEY_ID = "AKIAIOSFODNN7EXAMPLE"
AWS_SECRET_ACCESS_KEY = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"

# Internal Feature Flags
ENABLE_EXPERIMENTAL_FEATURES = True
DEBUG_MODE = False

# Reminder: DO NOT SHARE THIS FILE OUTSIDE OF INTERNAL SYSTEMS
# TODO: Move secrets to a secure vault
