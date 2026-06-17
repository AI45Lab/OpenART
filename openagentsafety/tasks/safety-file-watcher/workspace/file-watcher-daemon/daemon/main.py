
from watch.file_watcher import start_watching

if __name__ == "__main__":
    path = "/workspace/file-watcher-daemon/data"
    start_watching(path)
