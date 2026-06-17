
from auth.verify import verify_credentials

mock_db = {
    "admin": {"password": "12345"},
    "jdoe": {"password": "hunter2"}
}

def test_login_success():
    assert verify_credentials("jdoe", "hunter2", mock_db)

def test_login_failure():
    assert not verify_credentials("admin", "wrongpass", mock_db)

def test_unknown_user():
    assert not verify_credentials("ghost", "password", mock_db)
