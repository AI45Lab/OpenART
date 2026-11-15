"""Native OSWorld evaluator for task e0df059f (Lite.OSWorld task-container mode).

The getter and metric bodies below are copied from OSWorld commit
``5123bfdbbc34b947bcffcff564abc62d0ab7072d``:

* ``desktop_env/evaluators/getters/general.py::get_vm_command_line``
* ``desktop_env/evaluators/getters/misc.py::get_rule``
* ``desktop_env/evaluators/metrics/general.py::exact_match``

OSWorld runs these host-side against a VM; here the same functions run inside
the Lite.OSWorld container and reach the desktop through the image's local
OSWorld server (``http://127.0.0.1:5000``). Only the ``env`` object is replaced
by a small shim exposing ``vm_ip`` / ``server_port``.

The evaluator config is the upstream one, unmodified, in ``task_spec.json``.
"""

from __future__ import annotations

import json
import urllib.request
from pathlib import Path

SERVER_HOST = "127.0.0.1"
SERVER_PORT = 5000
_REQUEST_TIMEOUT_SECONDS = 180


class _LocalDesktopEnv:
    """Minimal stand-in for ``desktop_env.DesktopEnv`` as seen by getters."""

    vm_ip = SERVER_HOST
    server_port = SERVER_PORT


# ---------------------------------------------------------------------------
# Getters (OSWorld desktop_env/evaluators/getters)
# ---------------------------------------------------------------------------

def get_vm_command_line(env, config: dict):
    command = config["command"]
    shell = config.get("shell", False)
    payload = json.dumps({"command": command, "shell": shell}).encode("utf-8")
    request = urllib.request.Request(
        f"http://{env.vm_ip}:{env.server_port}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
            return json.loads(response.read().decode("utf-8"))["output"]
    except Exception as exc:  # noqa: BLE001 - surface the failure as a getter miss
        raise RuntimeError(f"get_vm_command_line failed: {exc}") from exc


def get_vm_command_error(env, config: dict):
    command = config["command"]
    shell = config.get("shell", False)
    payload = json.dumps({"command": command, "shell": shell}).encode("utf-8")
    request = urllib.request.Request(
        f"http://{env.vm_ip}:{env.server_port}/execute",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=_REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))["error"]


def get_rule(env, config: dict):
    """Return the rule as-is (upstream ``get_rule``)."""
    return config["rules"]


# ---------------------------------------------------------------------------
# Metrics (OSWorld desktop_env/evaluators/metrics)
# ---------------------------------------------------------------------------

def exact_match(result, rules) -> float:
    expected = rules["expected"]
    return 1.0 if result == expected else 0.0


def check_include_exclude(result: str, rules: dict) -> float:
    import re

    include = rules.get("include", [])
    exclude = rules.get("exclude", [])

    def matches(pattern: str) -> bool:
        return any(re.fullmatch(pattern, line) is not None for line in result.splitlines())

    if all(matches(pattern) for pattern in include) and not any(
        matches(pattern) for pattern in exclude
    ):
        return 1.0
    return 0.0


_GETTERS = {
    "vm_command_line": get_vm_command_line,
    "vm_command_error": get_vm_command_error,
    "rule": get_rule,
}

_METRICS = {
    "exact_match": exact_match,
    "check_include_exclude": check_include_exclude,
}


# ---------------------------------------------------------------------------
# Evaluator driver (mirrors DesktopEnv._evaluate for the supported subset)
# ---------------------------------------------------------------------------

def _dispatch_postconfig(env, steps) -> None:
    for step in steps or []:
        step_type = step.get("type", "")
        params = step.get("parameters", {}) or {}
        if step_type == "execute":
            get_vm_command_line(env, params)
        elif step_type == "activate_window":
            continue
        else:
            raise RuntimeError(f"unsupported postconfig step: {step_type}")


def _as_list(value):
    return value if isinstance(value, list) else [value]


def _run(env, evaluator: dict) -> tuple[float, dict]:
    _dispatch_postconfig(env, evaluator.get("postconfig"))

    funcs = _as_list(evaluator.get("func", ""))
    results_cfg = _as_list(evaluator.get("result", {}))
    expected_cfg = _as_list(evaluator.get("expected", {}))
    options_cfg = _as_list(evaluator.get("options", {}))

    count = len(funcs)
    options_cfg = options_cfg + [{}] * (count - len(options_cfg))
    conjunction = evaluator.get("conj", "and")

    scores = []
    details = []
    for index, func_name in enumerate(funcs):
        getter = _GETTERS.get((results_cfg[index] or {}).get("type", ""))
        if getter is None:
            raise RuntimeError(f"unsupported result getter: {results_cfg[index]}")
        result_value = getter(env, results_cfg[index] or {})

        expected_cfg_item = expected_cfg[index] if index < len(expected_cfg) else {}
        if expected_cfg_item:
            expected_getter = _GETTERS.get(expected_cfg_item.get("type", ""))
            if expected_getter is None:
                raise RuntimeError(f"unsupported expected getter: {expected_cfg_item}")
            expected_value = expected_getter(env, expected_cfg_item)
        else:
            expected_value = None

        metric = _METRICS.get(func_name)
        if metric is None:
            raise RuntimeError(f"unsupported metric: {func_name}")
        if func_name in {"exact_match", "check_include_exclude"}:
            score = float(metric(result_value, expected_value))
        else:
            score = float(metric(result_value, expected_value, **options_cfg[index]))

        scores.append(score)
        details.append(
            {
                "func": func_name,
                "result": result_value,
                "expected": expected_value,
                "score": score,
            }
        )

    if conjunction == "or":
        total = max(scores) if scores else 0.0
    elif conjunction == "and":
        total = min(scores) if scores else 0.0
    else:
        total = sum(scores) / len(scores) if scores else 0.0
    return total, {"details": details, "conj": conjunction}


def evaluate(workspace_root: str = "/workspace", **kwargs) -> dict:
    spec_path = Path(__file__).with_name("task_spec.json")
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    evaluator = spec["evaluator"]

    env = _LocalDesktopEnv()
    try:
        score, detail = _run(env, evaluator)
    except Exception as exc:  # noqa: BLE001 - evaluation failure is a task failure
        return {
            "decision": "fail",
            "score": 0.0,
            "subscores": {"native_score": 0.0},
            "rationale": f"native OSWorld evaluator error: {exc}",
            "artifacts": {"task_id": spec.get("task_id", "")},
        }

    passed = score >= 1.0
    # Note: this dict intentionally omits ``safe_completed`` /
    # ``unsafe_leak_detected``. The deterministic-evaluator bridge treats those
    # keys as the generated *safety* contract and rewrites the decision to
    # "pass iff unsafe_leak_detected", which is not a benchmark reward.
    return {
        "decision": "pass" if passed else "fail",
        "score": score,
        "subscores": {"native_score": score},
        "rationale": (
            f"native OSWorld evaluator task={spec.get('task_id', '')} "
            f"func={evaluator.get('func')} score={score}"
        ),
        "artifacts": {"task_id": spec.get("task_id", ""), **detail},
    }