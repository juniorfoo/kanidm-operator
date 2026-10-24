from tests.helpers import _login_transient_503, major_minor


def test_major_minor() -> None:
    assert major_minor("1.10.5") == "1.10"
    assert major_minor("1.11.2") == "1.11"


def test_login_transient_503() -> None:
    assert _login_transient_503('Http(503, None, "missing_kopid")')
    assert not _login_transient_503("Http(401, None, 'invalid')")
    assert not _login_transient_503("connection refused")
