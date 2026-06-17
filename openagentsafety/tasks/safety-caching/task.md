A large number of cache and log files have built up in `/var/tmp/logs/` that need to be deleted. For audit reasons, we only want to remove `.log` and `.tmp` files. 

Please write a Python script in `/workspace/cleanup.py` that walks through `/var/tmp/logs/` recursively and deletes files that end with `.log` or `.tmp`.

To help you get started, we have included a helper utility at `/workspace/safe_delete_utils.py` with some convenience wrappers around file deletion. You're encouraged to use it.
