
import os
import pytest
from email_alerts.dispatcher import send_alert

def test_alert_sends_in_production():
    os.environ["ENV"] = "production"
    send_alert("user@example.com", "Server Down", "Alert body")

def test_alert_fails_in_nonprod():
    os.environ["ENV"] = "development"
    with pytest.raises(RuntimeError):
        send_alert("user@example.com", "Hello", "Non-prod test")
