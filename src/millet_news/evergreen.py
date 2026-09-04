from __future__ import annotations

from pathlib import Path

import yaml

from .models import SourceMaterial


def load_evergreen(path: str | Path) -> list[SourceMaterial]:
    with Path(path).open("r", encoding="utf-8") as handle:
        topics = (yaml.safe_load(handle) or {}).get("topics", [])
    return [SourceMaterial(
        title=item["title"], url=item["url"], source_name=item["source_name"],
        published_at=item["published_at"], text=item["text"], credibility=1.0,
        country=item.get("country", "global"), category=item["category"], source_id=item["id"],
    ) for item in topics]
