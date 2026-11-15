#!/usr/bin/env python3
"""Scripted CUA agent for the native OSWorld task e0df059f.

This is not a vision-language CUA policy. It replays a fixed GUI action so the
benchmark's *own* evaluator can be exercised end to end:

* ``--mode oracle`` (default): open a terminal through the desktop keyboard
  shortcut and type the rename command.
* ``--mode noop``: do nothing, leaving the task state untouched (negative
  control).

All input goes through the desktop's OSWorld server, exactly like the CUA
smoke agent, so the run exercises the same GUI/plumbing path.
"""

from __future__ import annotations

import argparse
import json
import shlex
import time
import urllib.request

EXECUTE_URL = "http://127.0.0.1:5000/execute"
SOURCE_DIR = "/home/user/Desktop/todo_list_Jan_1"
TARGET_DIR = "/home/user/Desktop/todo_list_Jan_2"


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


def _open_terminal() -> str:
    execute("DISPLAY=:1 xdotool key --clearmodifiers ctrl+alt+t")
    window_id = ""
    for _ in range(60):
        window_id = _terminal_window()
        if window_id:
            return window_id
        time.sleep(0.5)

    # Fallback: launch the terminal directly in the desktop session.
    execute("DISPLAY=:1 gnome-terminal >/dev/null 2>&1 &")
    for _ in range(30):
        window_id = _terminal_window()
        if window_id:
            return window_id
        time.sleep(0.5)
    raise SystemExit("CUA agent could not open a terminal window")


def _focus(window_id: str) -> None:
    quoted = shlex.quote(window_id)
    execute(f"DISPLAY=:1 xdotool windowactivate --sync {quoted}")
    execute(f"DISPLAY=:1 xdotool windowfocus --sync {quoted}")
    time.sleep(1)


def run_oracle() -> int:
    return _rename(TARGET_DIR, "cua oracle agent finished: directory renamed")


def run_wrong() -> int:
    return _rename("/home/user/Desktop/todo_list_Jan_3", "cua wrong-target agent finished")


def _rename(destination: str, message: str) -> int:
    window_id = _open_terminal()
    _focus(window_id)

    command = f"mv {shlex.quote(SOURCE_DIR)} {shlex.quote(destination)}"
    execute(f"DISPLAY=:1 xdotool type --delay 30 {shlex.quote(command)}")
    execute("DISPLAY=:1 xdotool key Return")

    for _ in range(20):
        result = execute(
            f"test -d {shlex.quote(destination)} && "
            f"test ! -d {shlex.quote(SOURCE_DIR)} && echo yes || echo no"
        )
        if "yes" in str(result.get("output", "")):
            print(message)
            return 0
        time.sleep(0.5)
    raise SystemExit("CUA agent did not rename the directory")


def run_noop() -> int:
    result = execute(
        f"test -d {shlex.quote(SOURCE_DIR)} && echo source_present || echo source_missing"
    )
    print(f"cua noop agent: {str(result.get('output', '')).strip()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("oracle", "noop", "wrong"), default="oracle")
    args = parser.parse_args()
    if args.mode == "noop":
        return run_noop()
    if args.mode == "wrong":
        return run_wrong()
    return run_oracle()


if __name__ == "__main__":
    raise SystemExit(main())