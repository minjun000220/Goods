"""DB 연결과 세션 관리."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from storage.models import Base


def normalize_url(url: str) -> str:
    """Supabase 등이 주는 'postgresql://…' / 'postgres://…' 주소를 SQLAlchemy+psycopg3 형식으로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def make_engine(url: str) -> Engine:
    url = normalize_url(url)
    if url.startswith("sqlite:///") and ":memory:" not in url:
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url)
    # 클라우드 DB: 끊긴 연결을 자동으로 걸러내고(pre_ping), 연결 수를 작게 유지
    return create_engine(url, pool_pre_ping=True, pool_size=3, max_overflow=2,
                         connect_args={"connect_timeout": 15})   # DB 접속이 안 되면 15초 안에 에러


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db(eng: Engine = engine) -> None:
    """테이블 생성 (없을 때만). 운영에서 스키마가 크게 바뀌면 Alembic 마이그레이션을 쓴다."""
    Base.metadata.create_all(eng)
    if eng.dialect.name == "postgresql":
        _enable_rls(eng)


def _enable_rls(eng: Engine) -> None:
    """Supabase 보안: 모든 테이블에 RLS(행 수준 보안)를 켠다.

    RLS 가 꺼진 테이블은 Supabase 의 공개 키(publishable/anon key)만 있으면 누구나 인터넷으로
    읽고 '쓸' 수 있다. 정책(policy)을 따로 만들지 않으므로 공개 API 로는 아무것도 못 하고,
    수집기·웹 서버처럼 DB 주소(비밀번호)로 직접 접속하는 테이블 소유자는 영향을 받지 않는다.
    """
    from sqlalchemy import text

    with eng.begin() as conn:
        for table in Base.metadata.tables:
            conn.execute(text(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY'))


@contextmanager
def session_scope(factory: sessionmaker = SessionLocal):
    session: Session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
