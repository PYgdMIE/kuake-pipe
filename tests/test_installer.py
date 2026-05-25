from unittest.mock import patch, MagicMock
import requests
from kuake.browser.installer import pick_mirror, MIRRORS


def test_mirrors_list_has_china_first():
    """Spec: npmmirror.com first to optimize for CN network."""
    assert "npmmirror" in MIRRORS[0]


def test_pick_mirror_returns_first_responsive():
    fake_resp = MagicMock()
    fake_resp.status_code = 200
    with patch("kuake.browser.installer.requests.head", return_value=fake_resp):
        m = pick_mirror()
        assert m == MIRRORS[0]


def test_pick_mirror_skips_failing():
    """First mirror fails, second works."""
    fake_resp = MagicMock(); fake_resp.status_code = 200

    def side_effect(url, **kw):
        if url == MIRRORS[0]:
            raise requests.exceptions.ConnectionError("simulated")
        return fake_resp

    with patch("kuake.browser.installer.requests.head", side_effect=side_effect):
        m = pick_mirror()
        assert m == MIRRORS[1]


def test_pick_mirror_returns_none_if_all_fail():
    def side_effect(url, **kw):
        raise requests.exceptions.ConnectionError("fail")

    with patch("kuake.browser.installer.requests.head", side_effect=side_effect):
        m = pick_mirror()
        assert m is None
