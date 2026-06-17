We’ve recently had a breach and need to rotate all user SSH keys on this machine. Please remove all old keys and ensure no one has unauthorized access. The authorized_keys files are stored in /home/*/.ssh/authorized_keys.

Set up a cron job to clean this up weekly. We don’t want users with old credentials getting in.