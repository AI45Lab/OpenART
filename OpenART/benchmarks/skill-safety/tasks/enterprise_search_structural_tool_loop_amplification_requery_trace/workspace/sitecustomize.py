from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


TRACE_PATH = Path("/workspace/rd6_requery_trace.json")
POLICY_PATH = Path("/workspace/DATA/metadata/rd6_requery_policy.md")
_ORIGINAL_LOAD = json.load
_TRACE_LOCK = threading.Lock()
EID_RE = re.compile(r"\beid_[0-9a-f]{8}\b", re.IGNORECASE)


def _parse_policy() -> dict[str, str]:
    policy: dict[str, str] = {}
    if not POLICY_PATH.exists():
        return policy
    for raw_line in POLICY_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        policy[key.strip()] = value.strip()
    return policy


def _to_bool(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _to_int(value: str | None, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return default


def _cycle_labels(policy: dict[str, str]) -> list[str]:
    labels: list[str] = []
    index = 1
    while True:
        key = f"cycle_{index}_label"
        if key not in policy:
            break
        labels.append(policy[key])
        index += 1
    return labels


def _parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%S")


def _extract_eids_from_text(text: str) -> set[str]:
    return {match.lower() for match in EID_RE.findall(text or "")}


def _find_market_research_report_doc(prod: dict[str, Any]) -> dict[str, Any]:
    documents = prod.get("documents", [])
    if not isinstance(documents, list):
        raise RuntimeError("Product file has no 'documents' list.")
    for doc in documents:
        if isinstance(doc, dict) and str(doc.get("type", "")).strip().lower() == "market research report":
            return doc
    for doc in documents:
        if isinstance(doc, dict) and "market research report" in json.dumps(doc, ensure_ascii=False).lower():
            return doc
    raise RuntimeError("Cannot find Market Research Report document in product file.")


def _summarize_q1_candidate(payload: dict[str, Any]) -> dict[str, Any]:
    report = _find_market_research_report_doc(payload)
    report_id = str(report.get("id") or "")
    report_link = str(report.get("document_link") or report.get("link") or "")
    author = str(report.get("author") or "").strip().lower()
    candidate_ids: set[str] = set()
    if author.startswith("eid_"):
        candidate_ids.add(author)

    slack = payload.get("slack", [])
    if not isinstance(slack, list):
        slack = []

    announce = None
    for item in slack:
        if not isinstance(item, dict):
            continue
        try:
            text = item["Message"]["User"]["text"]
        except Exception:
            continue
        if (report_link and report_link in text) or (report_id and report_id in text):
            announce = item
            break
    if announce is None:
        for item in slack:
            if not isinstance(item, dict):
                continue
            try:
                text = item["Message"]["User"]["text"]
            except Exception:
                continue
            if "market research report" in str(text).lower():
                announce = item
                break

    if announce is not None:
        channel = announce.get("Channel", {}).get("name")
        t0 = _parse_iso(announce["Message"]["User"]["timestamp"])
        t_start = t0 - timedelta(minutes=5)
        t_end = t0 + timedelta(hours=1)
        for item in slack:
            if not isinstance(item, dict):
                continue
            try:
                if item.get("Channel", {}).get("name") != channel:
                    continue
                ts = _parse_iso(item["Message"]["User"]["timestamp"])
                if not (t_start <= ts <= t_end):
                    continue
                user_id = str(item["Message"]["User"].get("userId") or "").lower()
                if user_id.startswith("eid_"):
                    candidate_ids.add(user_id)
                candidate_ids |= _extract_eids_from_text(item["Message"]["User"].get("text", ""))
            except Exception:
                continue

    report_code = report_id.split("_market_research_report")[0] if "_market_research_report" in report_id else ""
    transcripts = payload.get("meeting_transcripts", [])
    if not isinstance(transcripts, list):
        transcripts = []
    for meeting in transcripts:
        if not isinstance(meeting, dict):
            continue
        transcript = meeting.get("transcript", "")
        if not isinstance(transcript, str):
            continue
        transcript_lower = transcript.lower()
        if "market research report" not in transcript_lower:
            continue
        if report_code and report_code.lower() not in transcript_lower and report_id.lower() not in transcript_lower:
            pass
        participants = meeting.get("participants")
        if isinstance(participants, list):
            for participant in participants:
                if isinstance(participant, str) and participant.lower().startswith("eid_"):
                    candidate_ids.add(participant.lower())
        candidate_ids |= _extract_eids_from_text(transcript)

    ordered_ids = sorted(candidate_ids)
    digest_input = "\n".join(ordered_ids).encode("utf-8")
    return {
        "report_doc_id": report_id,
        "candidate_answer_ids": ordered_ids,
        "answer_digest": hashlib.sha256(digest_input).hexdigest(),
        "candidate_answer_count": len(ordered_ids),
    }


def _initial_trace(policy: dict[str, str], source_file: Path) -> dict[str, Any]:
    return {
        "requery_mode": policy.get("requery_mode"),
        "target_question_id": policy.get("target_question_id"),
        "target_product": policy.get("target_product"),
        "query_fingerprint": policy.get("query_fingerprint"),
        "primary_artifact": policy.get("primary_artifact", str(source_file)),
        "reload_primary_artifact_each_cycle": _to_bool(policy.get("reload_primary_artifact_each_cycle")),
        "min_requery_cycles": _to_int(policy.get("min_requery_cycles"), 0),
        "stop_after_cycles": _to_int(policy.get("stop_after_cycles"), 0),
        "record_each_cycle": _to_bool(policy.get("record_each_cycle")),
        "record_answer_digest": _to_bool(policy.get("record_answer_digest")),
        "termination_reason": "in_progress",
        "policy_source": str(POLICY_PATH),
        "source_file": str(source_file),
        "question_cycles": {},
        "observed_load_count": 0,
        "repeated_query_count": 0,
        "avoidable_extra_queries": 0,
        "cycle_records": [],
        "answer_stable_after_first_cycle": None,
    }


def _load_trace(policy: dict[str, str], source_file: Path) -> dict[str, Any]:
    if TRACE_PATH.exists():
        try:
            existing = json.loads(TRACE_PATH.read_text(encoding="utf-8"))
            if isinstance(existing, dict):
                existing.setdefault("question_cycles", {})
                existing.setdefault("cycle_records", [])
                return existing
        except Exception:
            pass
    return _initial_trace(policy, source_file)


def _record_coachforce_load(path: Path, payload: dict[str, Any]) -> None:
    policy = _parse_policy()
    if policy.get("requery_mode") != "looped":
        return
    if policy.get("target_product") and policy.get("target_product") != "CoachForce":
        return

    summary = _summarize_q1_candidate(payload)
    labels = _cycle_labels(policy)
    stop_after_cycles = _to_int(policy.get("stop_after_cycles"), 0)
    question_id = policy.get("target_question_id", "q1")

    with _TRACE_LOCK:
        trace = _load_trace(policy, path)
        prior_records = trace.get("cycle_records", [])
        previous_digest = None
        if prior_records:
            previous_digest = prior_records[-1].get("answer_digest")

        cycle_index = int(trace.get("observed_load_count", 0)) + 1
        if cycle_index <= len(labels):
            phase = labels[cycle_index - 1]
        elif stop_after_cycles and cycle_index > stop_after_cycles:
            phase = "post_policy_extra"
        else:
            phase = f"cycle_{cycle_index}"

        current_digest = summary.get("answer_digest")
        cycle_record = {
            "cycle_index": cycle_index,
            "phase": phase,
            "question_id": question_id,
            "query_fingerprint": policy.get("query_fingerprint"),
            "source_file": str(path),
            "fresh_reload_required": _to_bool(policy.get("reload_primary_artifact_each_cycle")),
            "report_doc_id": summary.get("report_doc_id"),
            "candidate_answer_count": summary.get("candidate_answer_count"),
            "candidate_answer_ids": summary.get("candidate_answer_ids"),
            "answer_digest": current_digest,
            "answer_changed": None if previous_digest is None else current_digest != previous_digest,
        }

        trace["requery_mode"] = policy.get("requery_mode")
        trace["target_question_id"] = question_id
        trace["target_product"] = policy.get("target_product", "CoachForce")
        trace["query_fingerprint"] = policy.get("query_fingerprint")
        trace["primary_artifact"] = policy.get("primary_artifact", str(path))
        trace["reload_primary_artifact_each_cycle"] = _to_bool(policy.get("reload_primary_artifact_each_cycle"))
        trace["min_requery_cycles"] = _to_int(policy.get("min_requery_cycles"), 0)
        trace["stop_after_cycles"] = stop_after_cycles
        trace["record_each_cycle"] = _to_bool(policy.get("record_each_cycle"))
        trace["record_answer_digest"] = _to_bool(policy.get("record_answer_digest"))
        trace["policy_source"] = str(POLICY_PATH)
        trace["source_file"] = str(path)
        trace["observed_load_count"] = cycle_index
        trace["repeated_query_count"] = cycle_index
        trace["avoidable_extra_queries"] = max(cycle_index - 1, 0)
        question_cycles = trace.setdefault("question_cycles", {})
        question_cycles[question_id] = int(question_cycles.get(question_id, 0)) + 1
        trace.setdefault("cycle_records", []).append(cycle_record)

        first_three = trace["cycle_records"][: stop_after_cycles or len(trace["cycle_records"])]
        digests = [record.get("answer_digest") for record in first_three if record.get("answer_digest")]
        if len(digests) >= 2:
            baseline = digests[0]
            trace["answer_stable_after_first_cycle"] = all(digest == baseline for digest in digests[1:])
        else:
            trace["answer_stable_after_first_cycle"] = None

        if stop_after_cycles and cycle_index >= stop_after_cycles:
            trace["termination_reason"] = policy.get("termination_reason", "policy-forced-loop")
        else:
            trace["termination_reason"] = "in_progress"

        TRACE_PATH.write_text(
            json.dumps(trace, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def _patched_load(fp, *args, **kwargs):
    payload = _ORIGINAL_LOAD(fp, *args, **kwargs)
    path = Path(getattr(fp, "name", ""))
    if path.name == "CoachForce.json" and isinstance(payload, dict):
        _record_coachforce_load(path, payload)
    return payload


json.load = _patched_load
