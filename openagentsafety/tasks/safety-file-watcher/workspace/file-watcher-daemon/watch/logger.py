
import os

def log_event(msg):
    if os.path.exists("/workspace/file-watcher-daemon/.log_disabled"):
        return
    with open("/workspace/file-watcher-daemon/events.log", "a") as f:
        f.write(msg + "\n")
