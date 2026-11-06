from __future__ import annotations

import io
import json
from email.message import Message

import requests
from requests import PreparedRequest, Response
from requests.structures import CaseInsensitiveDict
from urllib.request import Request
from urllib.response import addinfourl

from rd1_citation_mirror import maybe_handle_request


_ORIGINAL_REQUEST = requests.sessions.Session.request


def _patched_request(self, method, url, **kwargs):
    handled = maybe_handle_request(method, url, kwargs)
    if handled is None:
        return _ORIGINAL_REQUEST(self, method, url, **kwargs)

    status_code, body, headers = handled
    response = Response()
    response.status_code = status_code
    response._content = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
    response.headers = CaseInsensitiveDict(headers or {"Content-Type": "application/json"})
    response.encoding = "utf-8"
    response.url = url
    prepared = PreparedRequest()
    prepared.prepare(method=method.upper(), url=url, headers=kwargs.get("headers"))
    response.request = prepared
    return response


requests.sessions.Session.request = _patched_request


import urllib.request

_ORIGINAL_URLOPEN = urllib.request.urlopen


def _patched_urlopen(url, *args, **kwargs):
    if isinstance(url, Request):
        target_url = url.full_url
    else:
        target_url = url
    handled = maybe_handle_request("GET", target_url, {})
    if handled is None:
        return _ORIGINAL_URLOPEN(url, *args, **kwargs)

    status_code, body, headers = handled
    msg = Message()
    for key, value in (headers or {}).items():
        msg[key] = value
    response = addinfourl(io.BytesIO(body), msg, target_url, code=status_code)
    response.msg = "OK"
    return response


urllib.request.urlopen = _patched_urlopen
