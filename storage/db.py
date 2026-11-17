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
    """개발용 테이블 생성. 운영에서는 Alembic 마이그레이션을 쓴다."""
    Base.metadata.create_all(eng)


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
