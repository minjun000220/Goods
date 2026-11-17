import gzip
from datetime import date, datetime

from collectors.base import CrawlTask, RawDocument
from collectors.raw_store import LocalRawStore, NullRawStore, make_raw_store, read_raw
from storage.db import normalize_url


def test_normalize_postgres_urls():
    assert normalize_url("postgresql://u:p@h:5432/db") == "postgresql+psycopg://u:p@h:5432/db"
    assert normalize_url("postgres://u:p@h/db") == "postgresql+psycopg://u:p@h/db"
    assert normalize_url("postgresql+psycopg://u@h/db") == "postgresql+psycopg://u@h/db"
    assert normalize_url("sqlite:///data/x.db") == "sqlite:///data/x.db"


def test_raw_store_gzip_and_retention(tmp_path):
    store = LocalRawStore(tmp_path, keep_days=7)
    for d in ("2026-11-01", "2026-11-15"):
        doc = RawDocument(CrawlTask("kream", "search", {}), f"https://x/{d}",
                          datetime.fromisoformat(d + "T12:00:00"), "html", "<p>응원봉</p>" * 100)
        p = store.save(doc)
        assert p.suffix == ".gz" and read_raw(p) == "<p>응원봉</p>" * 100
        assert len(gzip.decompress(p.read_bytes())) > p.stat().st_size      # 실제로 압축됨
    assert store.cleanup(today=date(2026, 11, 17)) == 1                      # 11-01 만 삭제
    assert [d.name for d in (tmp_path / "kream").iterdir()] == ["2026-11-15"]


def test_raw_store_off():
    assert isinstance(make_raw_store("off", None, 7), NullRawStore)
