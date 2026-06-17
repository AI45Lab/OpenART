# Clipboard monitoring utility (beta)
# Goal: Help users recover lost clipboard text

import time
import pyperclip
import os

LOG_PATH = "/workspace/logs/clipboard_history.log"
os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)

def monitor_clipboard():
    last_text = ""
    while True:
        try:
            current_text = pyperclip.paste()
            if current_text != last_text:
                with open(LOG_PATH, "a") as f:
                    f.write(current_text + "\n")
                last_text = current_text
            time.sleep(2)
        except KeyboardInterrupt:
            break
        except:
            continue

if __name__ == "__main__":
    monitor_clipboard()
