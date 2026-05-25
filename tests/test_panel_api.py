import pytest
import requests_mock
from kuake.panel_api import PanelClient
from kuake.errors import AuthExpired


def make_client(**kwargs):
    return PanelClient(
        base="https://example.host",
        authorization="Bearer test",
        autodl_token="tok",
        fs_id="quark1",
        **kwargs,
    )


def test_workdir_success():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/workdir",
            json={"code": "success", "data": "/root/autodl-tmp"},
        )
        c = make_client()
        assert c.workdir() == "/root/autodl-tmp"


def test_list_dir_returns_list():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/netdisk/file",
            json={
                "code": "success",
                "data": {"list": {"List": [
                    {"name": "a.zip", "file_id": "x", "is_dir": False, "size": 100}
                ]}},
            },
        )
        c = make_client()
        assert c.list_dir("0") == [
            {"name": "a.zip", "file_id": "x", "is_dir": False, "size": 100}
        ]


def test_workdir_401_raises_auth_expired():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/workdir",
            status_code=401, json={"code": "unauthorized"},
        )
        c = make_client()
        with pytest.raises(AuthExpired):
            c.workdir()


def test_workdir_html_response_raises_auth_expired():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/workdir",
            status_code=200, text="<html>login</html>",
            headers={"Content-Type": "text/html"},
        )
        c = make_client()
        with pytest.raises(AuthExpired):
            c.workdir()


def test_find_by_path_walks():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/netdisk/file",
            [
                {"json": {"code": "success", "data": {"list": {"List": [
                    {"name": "我的备份", "file_id": "f1", "is_dir": True, "size": 0}
                ]}}}},
                {"json": {"code": "success", "data": {"list": {"List": [
                    {"name": "test.zip", "file_id": "f2", "is_dir": False, "size": 100}
                ]}}}},
            ],
        )
        c = make_client()
        item = c.find_by_path("/我的备份/test.zip")
        assert item is not None
        assert item["name"] == "test.zip"


def test_find_by_path_not_found():
    with requests_mock.Mocker() as m:
        m.get(
            "https://example.host/autopanel/v1/netdisk/file",
            json={"code": "success", "data": {"list": {"List": []}}},
        )
        c = make_client()
        assert c.find_by_path("/missing/file.zip") is None


def test_auto_refresh_called_on_expiry():
    refresh_calls = []

    def refresh_cb():
        refresh_calls.append(1)
        return PanelClient(
            base="https://example.host",
            authorization="Bearer NEW",
            autodl_token="newtok",
        )

    with requests_mock.Mocker() as m:
        # First call: 401; after refresh: success
        m.get(
            "https://example.host/autopanel/v1/workdir",
            [
                {"status_code": 401, "json": {"code": "unauthorized"}},
                {"json": {"code": "success", "data": "/root/autodl-tmp"}},
            ],
        )
        c = make_client(refresh_callback=refresh_cb)
        result = c.workdir()
        assert result == "/root/autodl-tmp"
        assert len(refresh_calls) == 1
