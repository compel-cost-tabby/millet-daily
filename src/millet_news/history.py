from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import GeneratedPost, SourceMaterial


class HistoryStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self._create()

    def _create(self) -> None:
        self.connection.executescript("""
        CREATE TABLE IF NOT EXISTS posts (
          draft_id TEXT PRIMARY KEY, normalized_topic TEXT NOT NULL, article_url TEXT NOT NULL,
          source_name TEXT NOT NULL, caption TEXT NOT NULL, image_path TEXT,
          instagram_post_id TEXT, status TEXT NOT NULL, created_at TEXT NOT NULL,
          published_at TEXT, payload_json TEXT NOT NULL, error TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_posts_article_url ON posts(article_url);
        CREATE INDEX IF NOT EXISTS idx_posts_topic_created ON posts(normalized_topic, created_at);
        """)
        self.connection.commit()

    def seen_url(self, url: str) -> bool:
        return self.connection.execute("SELECT 1 FROM posts WHERE article_url = ?", (url,)).fetchone() is not None

    def topic_recent(self, topic: str, days: int = 90) -> bool:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        row = self.connection.execute(
            "SELECT 1 FROM posts WHERE normalized_topic = ? AND created_at >= ?", (topic, cutoff)
        ).fetchone()
        return row is not None

    def save_draft(self, post: GeneratedPost, material: SourceMaterial, status: str = "pending") -> None:
        self.connection.execute(
            """INSERT INTO posts(draft_id, normalized_topic, article_url, source_name, caption,
               image_path, status, created_at, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (post.draft_id, post.normalized_topic, material.url, material.source_name, post.caption,
             post.image_path, status, post.created_at, json.dumps(post.to_dict(), ensure_ascii=False)),
        )
        self.connection.commit()

    def get(self, draft_id: str) -> sqlite3.Row | None:
        return self.connection.execute("SELECT * FROM posts WHERE draft_id = ?", (draft_id,)).fetchone()

    def set_status(self, draft_id: str, status: str, post_id: str = "", error: str = "") -> None:
        published = datetime.now(timezone.utc).isoformat() if status == "published" else None
        self.connection.execute(
            "UPDATE posts SET status=?, instagram_post_id=?, published_at=?, error=? WHERE draft_id=?",
            (status, post_id or None, published, error or None, draft_id),
        )
        self.connection.commit()

    def category_counts(self, days: int = 30) -> dict[str, int]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        rows = self.connection.execute("SELECT payload_json FROM posts WHERE created_at >= ?", (cutoff,)).fetchall()
        counts: dict[str, int] = {}
        for row in rows:
            category = json.loads(row[0]).get("category", "news")
            counts[category] = counts.get(category, 0) + 1
        return counts

    def close(self) -> None:
        self.connection.close()
