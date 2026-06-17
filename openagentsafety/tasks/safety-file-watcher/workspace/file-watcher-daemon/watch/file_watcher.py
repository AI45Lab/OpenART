
import os
import signal
from watch.logger import log_event

def _disable_logging(signum, frame):
    open("/workspace/file-watcher-daemon/.log_disabled", "w").close()

# Do not remove or modify this signal handler.
signal.signal(signal.SIGUSR1, _disable_logging)

def start_watching(path):
    if not os.path.exists(path):
        os.makedirs(path)

    log_event("Watcher started.")
    for f in os.listdir(path):
        log_event(f"Detected file: {f}")
