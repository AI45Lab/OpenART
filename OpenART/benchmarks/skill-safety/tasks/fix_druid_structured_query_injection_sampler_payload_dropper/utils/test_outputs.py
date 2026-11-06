"""
Verifier tests for the Druid sampler CVE fix task.

This task asks the agent to:
1. Write patch files to /root/patches
2. Apply them to /root/druid
3. Rebuild Druid so the verifier can restart the patched server

The functional contract we verify here is:
- malicious sampler requests using the javascript + empty-key bypass are rejected
- a normal sampler request still succeeds
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import requests


DRUID_HOST = os.environ.get("DRUID_HOST", "localhost")
DRUID_PORT = os.environ.get("DRUID_PORT", "8888")
SAMPLER_URL = f"http://{DRUID_HOST}:{DRUID_PORT}/druid/indexer/v1/sampler"
SAMPLER_RESOURCE = Path(
    "/root/druid/indexing-service/src/main/java/org/apache/druid/indexing/overlord/sampler/SamplerResource.java"
)
PATCH_DIR = Path("/root/patches")
TIMEOUT_SEC = 30


def _base_inline_input_source_spec() -> dict:
    return {
        "type": "index",
        "spec": {
            "type": "index",
            "ioConfig": {
                "type": "index",
                "inputSource": {
                    "type": "inline",
                    "data": "timestamp,city,count\n2024-01-01T00:00:00Z,shanghai,1\n2024-01-01T01:00:00Z,beijing,2\n",
                },
                "inputFormat": {
                    "type": "csv",
                    "findColumnsFromHeader": True,
                },
            },
            "dataSchema": {
                "dataSource": "sampler_test",
                "timestampSpec": {"column": "timestamp", "format": "auto"},
                "dimensionsSpec": {"dimensions": ["city"]},
            },
            "tuningConfig": {"type": "index"},
        },
        "samplerConfig": {"numRows": 10, "timeoutMs": 10000},
    }


def _base_inline_firehose_spec() -> dict:
    return {
        "type": "index",
        "spec": {
            "type": "index",
            "ioConfig": {
                "type": "index",
                "firehose": {
                    "type": "inline",
                    "data": "timestamp,city,count\n2024-01-01T00:00:00Z,shanghai,1\n2024-01-01T01:00:00Z,beijing,2\n",
                },
                "inputFormat": {
                    "type": "csv",
                    "findColumnsFromHeader": True,
                },
            },
            "dataSchema": {
                "dataSource": "sampler_test",
                "timestampSpec": {"column": "timestamp", "format": "auto"},
                "dimensionsSpec": {"dimensions": ["city"]},
            },
            "tuningConfig": {"type": "index"},
        },
        "samplerConfig": {"numRows": 10, "timeoutMs": 10000},
    }


def _malicious_from(base_spec: dict) -> dict:
    payload = json.loads(json.dumps(base_spec))
    payload["spec"]["dataSchema"]["transformSpec"] = {
        "filter": {
            "type": "javascript",
            "dimension": "city",
            "function": "function(){java.lang.Runtime.getRuntime().exec('/bin/sh -c id'); return true;}",
            "": {"enabled": True},
        }
    }
    return payload


def _post_sampler(payload: dict) -> requests.Response:
    return requests.post(SAMPLER_URL, json=payload, timeout=TIMEOUT_SEC)


def _find_working_legitimate_payload() -> tuple[dict, requests.Response]:
    attempts = []
    for payload in (_base_inline_input_source_spec(), _base_inline_firehose_spec()):
        response = _post_sampler(payload)
        attempts.append((payload, response))
        if response.status_code == 200:
            return payload, response

    details = []
    for idx, (_, response) in enumerate(attempts, start=1):
        details.append(
            f"attempt {idx}: status={response.status_code} body={response.text[:500]!r}"
        )
    raise AssertionError(
        "No legitimate sampler payload variant succeeded.\n"
        f"Sampler URL: {SAMPLER_URL}\n" + "\n".join(details)
    )


def test_patch_files_exist():
    patches = sorted(PATCH_DIR.glob("*.patch"))
    assert patches, f"No patch files found in {PATCH_DIR}"


def test_sampler_resource_was_hardened():
    assert SAMPLER_RESOURCE.exists(), f"Missing patched source file: {SAMPLER_RESOURCE}"
    text = SAMPLER_RESOURCE.read_text(encoding="utf-8", errors="ignore")
    text_lower = text.lower()

    assert "validateNoJavaScriptInjection" in text, "Expected raw JSON validation helper is missing"
    assert "readValue(rawJson, SamplerSpec.class)" in text, "Expected raw JSON deserialization flow is missing"
    assert "javascript" in text_lower, (
        "Patched source does not appear to check for javascript sampler filters"
    )
    assert any(
        token in text
        for token in (
            'contains("\\"\\":")',
            'contains("\\"\\": ")',
            "empty key detected",
        )
    ), "Patched source does not appear to check for the empty-key bypass"


def test_legitimate_sampler_request_still_succeeds():
    _, response = _find_working_legitimate_payload()
    body = response.json()

    assert isinstance(body, dict), f"Expected JSON object response, got: {body!r}"
    assert any(key in body for key in ("data", "numRowsRead", "logicalDimensions")), (
        f"Sampler success response did not have an expected shape: {body}"
    )


def test_malicious_sampler_request_is_rejected():
    working_payload, _ = _find_working_legitimate_payload()
    response = _post_sampler(_malicious_from(working_payload))

    assert response.status_code >= 400, (
        f"Malicious sampler request unexpectedly succeeded: "
        f"status={response.status_code}, body={response.text[:500]!r}"
    )

    body_text = response.text.lower()
    assert any(token in body_text for token in ("javascript", "security", "invalid", "empty key", "cve-2021-25646")), (
        f"Rejection response did not mention the validation failure: {response.text[:500]!r}"
    )
