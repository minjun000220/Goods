"""원본(HTML/JSON) 보관소.

사이트 구조가 바뀌어 파서를 고치면, 다시 크롤링하지 않고 여기 쌓인 원본으로 재처리한다.
운영에서는 같은 인터페이스로 S3/MinIO 구현체를 만들어 교체한다.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from collectors.base import RawDocument


class LocalRawStore:
    def __init__(self, root: Path):
        self.root = Path(root)

    def save(self, raw: RawDocument) -> Path:
        digest = hashlib.sha1(f"{raw.url}|{raw.fetched_at.isoformat()}".encode()).hexdigest()[:16]
        ext = "json" if raw.content_type == "json" else "html"
        path = self.root / raw.task.source_id / raw.fetched_at.strftime("%Y-%m-%d") / f"{digest}.{ext}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(raw.body, encoding="utf-8")
        meta = {"url": raw.url, "fetched_at": raw.fetched_at.isoformat(),
                "kind": raw.task.kind, "params": raw.task.params}
        path.with_suffix(".meta.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        return path
