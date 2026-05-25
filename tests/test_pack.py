import hashlib
import zipfile
from kuake.pack import make_zip, md5sum


def test_make_zip_from_file(tmp_path):
    src = tmp_path / "hello.txt"
    src.write_text("hello world")
    out = tmp_path / "out.zip"
    make_zip(src, out)
    assert out.exists()
    with zipfile.ZipFile(out) as zf:
        assert zf.namelist() == ["hello.txt"]
        assert zf.read("hello.txt").decode() == "hello world"


def test_make_zip_from_dir(tmp_path):
    d = tmp_path / "data"
    d.mkdir()
    (d / "a.txt").write_text("a")
    (d / "sub").mkdir()
    (d / "sub" / "b.txt").write_text("b")
    out = tmp_path / "out.zip"
    make_zip(d, out)
    with zipfile.ZipFile(out) as zf:
        names = sorted(zf.namelist())
        assert names == ["a.txt", "sub/b.txt"]


def test_md5sum_matches_hashlib(tmp_path):
    p = tmp_path / "x"
    p.write_bytes(b"deterministic content")
    expected = hashlib.md5(b"deterministic content").hexdigest()
    assert md5sum(p) == expected


def test_make_zip_creates_parent(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("x")
    out = tmp_path / "nested" / "deeper" / "out.zip"
    make_zip(src, out)
    assert out.exists()
