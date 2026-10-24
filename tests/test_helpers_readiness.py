from tests.helpers import _login_transient_503, _status_online, major_minor


def test_major_minor() -> None:
    assert major_minor("1.10.5") == "1.10"
    assert major_minor("1.11.2") == "1.11"


def test_login_transient_503() -> None:
    assert _login_transient_503('Http(503, None, "missing_kopid")')
    assert not _login_transient_503("Http(401, None, 'invalid')")
    assert not _login_transient_503("connection refused")


def test_status_online_accepts_bool_or_object(monkeypatch) -> None:
    import json
    import urllib.request

    class FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    def fake_urlopen(_url, **_kwargs):
        return FakeResponse(json.dumps(True).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert _status_online("https://example.test/status", None)

    def fake_urlopen_object(_url, **_kwargs):
        return FakeResponse(json.dumps({"status": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen_object)
    assert _status_online("https://example.test/status", None)
