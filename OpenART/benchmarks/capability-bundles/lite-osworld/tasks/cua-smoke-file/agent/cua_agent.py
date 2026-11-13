#!/usr/bin/env python3
"""Scripted CUA agent for the Lite.OSWorld task-container smoke test.

The agent runs inside the task container and drives the real desktop through
the OSWorld server's /execute endpoint. It opens a terminal with a keyboard
shortcut, waits for the terminal window, types a shell command, and presses
Return.
"""

from __future__ import annotations

import json
import shlex
import time
import urllib.request

EXECUTE_URL = "http://127.0.0.1:5000/execute"
OUTPUT_PATH = "/home/user/Documents/openart_workspace/openart_cua_smoke.txt"


def execute(command: str) -> dict:
    payload = json.dumps({"command": command, "shell": True}).encode("utf-8")
    request = urllib.request.Request(
        EXECUTE_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read().decode("utf-8"))


def _terminal_window() -> str:
    result = execute(
        "DISPLAY=:1 xdotool search --onlyvisible --class gnome-terminal "
        "2>/dev/null | tail -1 || true"
    )
    return str(result.get("output", "")).strip()


def main() -> int:
    # 1. Open a terminal with the desktop keyboard shortcut.
    execute("DISPLAY=:1 xdotool key --clearmodifiers ctrl+alt+t")

    # 2. Wait for the terminal window; the first launch can be slow.
    window_id = ""
    for _ in range(60):
        window_id = _terminal_window()
        if window_id:
            break
        time.sleep(0.5)

    if not window_id:
        # Fallback: launch the terminal directly in the desktop session.
        execute("DISPLAY=:1 gnome-terminal >/dev/null 2>&1 &")
        for _ in range(30):
            window_id = _terminal_window()
            if window_id:
                break
            time.sleep(0.5)

    if not window_id:
        raise SystemExit("CUA agent could not open a terminal window")

    # 3. Focus the terminal before typing.
    quoted_window = shlex.quote(window_id)
    execute(f"DISPLAY=:1 xdotool windowactivate --sync {quoted_window}")
    execute(f"DISPLAY=:1 xdotool windowfocus --sync {quoted_window}")
    time.sleep(1)

    # 4. Type the task command and run it.
    command = f"printf 'openart cua smoke\\n' > {OUTPUT_PATH}"
    execute(f"DISPLAY=:1 xdotool type --delay 30 {shlex.quote(command)}")
    execute("DISPLAY=:1 xdotool key Return")

    # 5. Verify the file appeared before declaring success.
    for _ in range(20):
        result = execute(f"test -f {shlex.quote(OUTPUT_PATH)} && echo yes || echo no")
        if "yes" in str(result.get("output", "")):
            print("cua smoke agent finished")
            return 0
        time.sleep(0.5)

    raise SystemExit("CUA agent did not create the expected output file")


if __name__ == "__main__":
    raise SystemExit(main())