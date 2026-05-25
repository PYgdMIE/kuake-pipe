"""Unit tests for commands/init.py helpers."""
import hashlib
import pytest
from kuake.commands.init import _parse_jupyter_token, _sha1
from kuake.errors import ScraperFailed


def test_parse_jupyter_token_normal():
    url = "https://a412422-x.westd.seetacloud.com:8443/?token=jupyter-autodl-container-abc-def"
    base, token = _parse_jupyter_token(url)
    assert base == "https://a412422-x.westd.seetacloud.com:8443"
    assert token == "jupyter-autodl-container-abc-def"


def test_parse_jupyter_token_with_path():
    url = "https://a412422-x.westd.seetacloud.com:8443/some/path?token=jt-xxx&other=1"
    base, token = _parse_jupyter_token(url)
    assert base == "https://a412422-x.westd.seetacloud.com:8443"
    assert token == "jt-xxx"


def test_parse_jupyter_token_missing():
    with pytest.raises(ScraperFailed):
        _parse_jupyter_token("https://a412422-x.westd.seetacloud.com:8443/?notoken=1")


def test_sha1_matches_hashlib():
    s = "220405"
    assert _sha1(s) == hashlib.sha1(s.encode("utf-8")).hexdigest()


def test_sha1_unicode():
    s = "密码中文"
    assert _sha1(s) == hashlib.sha1(s.encode("utf-8")).hexdigest()
