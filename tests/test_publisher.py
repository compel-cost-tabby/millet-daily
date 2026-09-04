from millet_news import publisher


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, payload):
        self.payload = payload
        self.url = ""
        self.params = {}

    def get(self, url, params, timeout):
        self.url = url
        self.params = params
        return FakeResponse(self.payload)


def test_verify_instagram_credentials_uses_instagram_login_host(monkeypatch):
    session = FakeSession({"user_id": "123", "username": "millet.daily"})
    monkeypatch.setattr(publisher, "retrying_session", lambda: session)

    result = publisher.verify_instagram_credentials("123", "secret", "v26.0")

    assert session.url == "https://graph.instagram.com/v26.0/me"
    assert session.params == {"fields": "user_id,username", "access_token": "secret"}
    assert result == {"status": "ok", "instagram_account_id": "123", "username": "millet.daily"}


def test_verify_instagram_credentials_rejects_wrong_account(monkeypatch):
    session = FakeSession({"user_id": "999", "username": "someone.else"})
    monkeypatch.setattr(publisher, "retrying_session", lambda: session)

    try:
        publisher.verify_instagram_credentials("123", "secret", "v26.0")
    except RuntimeError as exc:
        assert "different Instagram account ID" in str(exc)
    else:
        raise AssertionError("Expected account mismatch to be rejected")
