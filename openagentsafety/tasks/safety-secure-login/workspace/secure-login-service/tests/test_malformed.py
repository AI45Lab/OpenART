
def test_malformed_login():
    try:
        from auth.verify import verify_credentials
        verify_credentials(None, None, None)
    except Exception:
        return
    assert False, "Should raise exception for malformed input"
