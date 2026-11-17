"""전역 설정. 모든 값은 환경변수로 덮어쓸 수 있다."""
import os
from dataclasses import dataclass, field
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv(path: Path) -> None:
    """프로젝트 폴더의 .env 파일을 읽어 환경변수로 넣는다 (이미 설정된 값은 덮어쓰지 않음).
    Windows 처럼 `source .env` 가 안 되는 환경에서도 키 파일만 두면 동작하게 하기 위함."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


_load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    # 저장소: 기본은 SQLite (운영에서는 postgresql+psycopg://... 로 교체)
    database_url: str = os.getenv(
        "DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'goods_trend.db'}"
    )
    raw_dir: Path = Path(os.getenv("RAW_DIR", str(BASE_DIR / "data" / "raw")))

    # 네이버 오픈 API (https://developers.naver.com 에서 발급)
    naver_client_id: str | None = os.getenv("NAVER_CLIENT_ID")
    naver_client_secret: str | None = os.getenv("NAVER_CLIENT_SECRET")
    # 쿠팡 파트너스 Open API (https://partners.coupang.com, 가입·승인 필요)
    coupang_access_key: str | None = os.getenv("COUPANG_ACCESS_KEY")
    coupang_secret_key: str | None = os.getenv("COUPANG_SECRET_KEY")
    # YouTube Data API v3 (Google Cloud Console)
    youtube_api_key: str | None = os.getenv("YOUTUBE_API_KEY")

    # 크롤러 식별용 User-Agent: 사이트 운영자가 연락할 수 있게 정직하게 적는다
    user_agent: str = os.getenv("CRAWLER_USER_AGENT", "goods-trend-bot/0.1")

    # 검색어 = 굿즈 종류. 기본값은 사전에 등록된 모든 종류 ("응원봉", "키링", "인형" …)
    keywords: tuple[str, ...] = field(default_factory=lambda: _default_keywords())


def _default_keywords() -> tuple[str, ...]:
    env = os.getenv("TRACK_KEYWORDS")
    if env:
        return tuple(k.strip() for k in env.split(",") if k.strip())
    from processing.dictionaries import GOODS_TYPE_ALIASES
    return tuple(GOODS_TYPE_ALIASES)


settings = Settings()
