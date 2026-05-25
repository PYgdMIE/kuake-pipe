"""Unit tests for the pure-logic parse helpers in autodl_scraper."""
from kuake.browser.autodl_scraper import _parse_row_meta, parse_ssh_command


def test_parse_row_meta_running():
    text = (
        "西北B区 / C37机\n"
        "fpd56n0x5y-24f47a8d\n"
        "设置名称\n"
        "运行中\n"
        "RTX PRO 6000 * 1卡\n"
        "查看快照"
    )
    m = _parse_row_meta(text)
    assert m["name"] == "西北B区 / C37机"
    assert m["status"] == "运行中"
    assert "RTX PRO 6000" in m["gpu"]


def test_parse_row_meta_stopped():
    text = (
        "西北B区 / 034机\n"
        "34894dbefa-127e6e29\n"
        "设置名称\n"
        "已关机\n"
        "vGPU-32GB * 1卡\n"
    )
    m = _parse_row_meta(text)
    assert m["name"] == "西北B区 / 034机"
    assert m["status"] == "已关机"
    assert "vGPU-32GB" in m["gpu"]


def test_parse_row_meta_booting():
    text = "西北B区 / X1机\nid-xxx\n开机中\nA100 * 1卡\n"
    m = _parse_row_meta(text)
    assert "开机中" in m["status"]


def test_parse_row_meta_no_status():
    text = "Unknown row\nno status keyword"
    m = _parse_row_meta(text)
    assert m["status"] == "未知"


def test_parse_ssh_command_valid():
    cmd = "ssh -p 15612 root@connect.westd.seetacloud.com"
    host, port, user = parse_ssh_command(cmd)
    assert host == "connect.westd.seetacloud.com"
    assert port == 15612
    assert user == "root"


def test_parse_ssh_command_with_padding():
    cmd = "Some prefix ssh -p 12345 myuser@my.host.com extra"
    host, port, user = parse_ssh_command(cmd)
    assert host == "my.host.com"
    assert port == 12345
    assert user == "myuser"


def test_parse_ssh_command_invalid():
    import pytest
    from kuake.errors import ScraperFailed
    with pytest.raises(ScraperFailed):
        parse_ssh_command("not an ssh command at all")
