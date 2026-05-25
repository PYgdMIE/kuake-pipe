from kuake.panel_api import is_expired_response


class _MockResp:
    def __init__(self, status_code, content_type, json_data, raises_on_json=False):
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self._json = json_data
        self._raises = raises_on_json

    def json(self):
        if self._raises:
            raise ValueError("not json")
        return self._json


def test_expired_on_401():
    r = _MockResp(401, "application/json", {"code": "unauthorized"})
    assert is_expired_response(r) is True


def test_expired_on_html_response():
    r = _MockResp(200, "text/html", None, raises_on_json=True)
    assert is_expired_response(r) is True


def test_expired_on_code_auth_expired():
    r = _MockResp(200, "application/json", {"code": "auth_expired"})
    assert is_expired_response(r) is True


def test_expired_on_code_unauthorized():
    r = _MockResp(200, "application/json", {"code": "unauthorized"})
    assert is_expired_response(r) is True


def test_not_expired_on_success():
    r = _MockResp(200, "application/json", {"code": "success", "data": {}})
    assert is_expired_response(r) is False


def test_not_expired_on_ok():
    r = _MockResp(200, "application/json", {"code": "ok"})
    assert is_expired_response(r) is False


def test_not_expired_when_json_unparseable_but_not_html():
    r = _MockResp(200, "application/octet-stream", None, raises_on_json=True)
    assert is_expired_response(r) is False
