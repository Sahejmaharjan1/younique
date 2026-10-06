from younique.core.security import session_cookie


def test_session_cookie_attributes_are_host_only() -> None:
    header = session_cookie("token", secure=True)
    assert "__Host-session=" in header
    assert "Secure" in header
    assert "HttpOnly" in header
    assert "Domain" not in header
