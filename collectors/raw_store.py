"""원본(HTML/JSON) 보관소.

사이트 구조가 바뀌어 파서를 고치면, 다시 크롤링하지 않고 여기 쌓인 원본으로 재처리한다.
- gzip 압축 저장 (실측 약 1/6 크기)
- keep_days 보다 오래된 날짜 폴더는 자동 삭제 (용량이 계속 쌓이지 않게). 0 이면 영구 보관
- 지워지는 것은 '원본 페이지'뿐이다. 분석 데이터(DB)는 절대 지우지 않는다
- RAW_STORE=off 면 저장하지 않는다 (GitHub Actions 처럼 디스크가 매번 사라지는 환경)
"""
from __future__ import annotations

import gzip
import hashlib
import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from collectors.base import RawDocument


class NullRawStore:
    def save(self, raw: RawDocument) -> None:
        return None

    def cleanup(self) -> int:
        return 0


class LocalRawStore:
    def __init__(self, root: Path, keep_days: int = 7, compress: bool = True):
        self.root = Path(root)
        self.keep_days = keep_days
        self.compress = compress

    def save(self, raw: RawDocument) -> Path:
        digest = hashlib.sha1(f"{raw.url}|{raw.fetched_at.isoformat()}".encode()).hexdigest()[:16]
        ext = "json" if raw.content_type == "json" else "html"
        path = self.root / raw.task.source_id / raw.fetched_at.strftime("%Y-%m-%d") / f"{digest}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = raw.body.encode("utf-8")
        if self.compress:
            path = path.with_name(path.name + ".gz")
            path.write_bytes(gzip.compress(data))
        else:
            path.write_bytes(data)
        meta = {"url": raw.url, "fetched_at": raw.fetched_at.isoformat(),
                "kind": raw.task.kind, "params": raw.task.params}
        path.with_name(f"{digest}.meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return path

    def cleanup(self, today: date | None = None) -> int:
        """keep_days 보다 오래된 날짜 폴더 삭제. 지운 폴더 수를 돌려준다. keep_days<=0 이면 영구 보관."""
        if self.keep_days <= 0 or not self.root.exists():
            return 0
        cutoff = (today or date.today()) - timedelta(days=self.keep_days)
        removed = 0
        for day_dir in self.root.glob("*/*"):
            try:
                d = date.fromisoformat(day_dir.name)
            except ValueError:
                continue
            if day_dir.is_dir() and d < cutoff:
                shutil.rmtree(day_dir)
                removed += 1
        return removed


def read_raw(path: Path) -> str:
    """보관된 원본 읽기 (압축 여부 자동 판별) — 재처리할 때 사용."""
    data = Path(path).read_bytes()
    return (gzip.decompress(data) if str(path).endswith(".gz") else data).decode("utf-8")


def make_raw_store(mode: str, root: Path, keep_days: int):
    if mode == "off":
        return NullRawStore()
    return LocalRawStore(root, keep_days=keep_days)
