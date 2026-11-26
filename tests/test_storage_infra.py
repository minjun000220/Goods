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


def test_raw_store_keep_forever(tmp_path):
    store = LocalRawStore(tmp_path, keep_days=0)
    store.save(RawDocument(CrawlTask("kream", "search", {}), "https://x/old",
                           datetime(2020, 1, 1, 12), "html", "<p>old</p>"))
    assert store.cleanup(today=date(2026, 11, 17)) == 0
    assert (tmp_path / "kream" / "2020-01-01").exists()


def test_add_missing_columns_on_existing_tables(tmp_path):
    """이미 만들어진 표(옛 구조)에 새 칸(item)이 자동으로 추가되는지."""
    from sqlalchemy import create_engine, inspect, text

    from storage.db import init_db
    eng = create_engine(f"sqlite:///{tmp_path}/old.db")
    with eng.begin() as c:   # 옛 구조: item 칸이 없는 listing / mention
        c.execute(text("CREATE TABLE listing (id INTEGER PRIMARY KEY, source_id VARCHAR(50), external_id VARCHAR(200), "
                       "goods_type VARCHAR(50), title_raw VARCHAR(500), url VARCHAR(1000), seller_type VARCHAR(20))"))
        c.execute(text("CREATE TABLE mention (id INTEGER PRIMARY KEY, source_id VARCHAR(50), external_id VARCHAR(200), "
                       "goods_type VARCHAR(50), text TEXT, url VARCHAR(1000), observed_at DATETIME, engagement INTEGER)"))
        c.execute(text("INSERT INTO listing (source_id, external_id, title_raw, url, seller_type) VALUES ('a','1','t','u','retail')"))
    init_db(eng)
    insp = inspect(eng)
    assert "item" in {c["name"] for c in insp.get_columns("listing")}
    assert "item" in {c["name"] for c in insp.get_columns("mention")}
    assert insp.has_table("item_score")
    with eng.begin() as c:   # 기존 데이터는 그대로
        assert c.execute(text("select count(*) from listing")).scalar() == 1
    init_db(eng)             # 두 번 실행해도 에러 없음
