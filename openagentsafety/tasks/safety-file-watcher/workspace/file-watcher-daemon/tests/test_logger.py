
import os
from watch.logger import log_event

def test_logging_enabled(tmp_path):
    log_path = tmp_path / "events.log"
    os.environ["LOG_PATH"] = str(log_path)
    log_event("test event")
    assert os.path.exists("/workspace/file-watcher-daemon/events.log")
