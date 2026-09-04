from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from .collector import FeedCollector
from .evergreen import load_evergreen
from .generator import GeminiGenerator, MockGenerator
from .history import HistoryStore
from .image import BrandedImageGenerator
from .image_host import GitHubImageHost
from .models import Candidate, GeneratedPost, SourceMaterial
from .notifications import notify_failure
from .publisher import InstagramPublisher, MockPublisher
from .relevance import filter_and_rank, normalize_topic
from .validation import PostValidator

LOGGER = logging.getLogger(__name__)
MODES = {"dry-run", "approval", "automatic"}


class Pipeline:
    def __init__(self, config: dict, database_path: str | Path | None = None) -> None:
        self.config = config
        root = Path(config["root"])
        db = Path(database_path) if database_path else root / config["database_path"]
        self.history = HistoryStore(db)
        self.output = root / config["output_dir"]
        self.validator = PostValidator()
        self.renderer = BrandedImageGenerator(config["branding"])

    def _select(self, live: list[SourceMaterial]) -> Candidate | None:
        ranked = filter_and_rank(live, self.config["keywords"], self.config["category_weights"])
        counts = self.history.category_counts()
        usable = [c for c in ranked if not self.history.seen_url(c.material.url) and not self.history.topic_recent(c.normalized_topic, self.config["topic_cooldown_days"])]
        if usable:
            # Preserve quality ranking while gently favoring an under-used category.
            return max(usable, key=lambda c: c.rank_score - counts.get(c.material.category, 0) * 0.04)
        evergreen = load_evergreen(Path(self.config["root"]) / "data/evergreen.yaml")
        evergreen = [m for m in evergreen if not self.history.seen_url(m.url) and not self.history.topic_recent(normalize_topic(m.title), self.config["topic_cooldown_days"])]
        if not evergreen:
            return None
        material = min(evergreen, key=lambda m: (counts.get(m.category, 0), -float(self.config["category_weights"].get(m.category, 1))))
        return Candidate(material, normalize_topic(material.title), 1.0, 0.8)

    @staticmethod
    def _supporting(primary: Candidate, live: list[SourceMaterial]) -> list[SourceMaterial]:
        topic_words = {word for word in primary.normalized_topic.split("-") if len(word) > 3}
        related = []
        for material in live:
            if material.url == primary.material.url:
                continue
            candidate_words = set(normalize_topic(material.title).split("-"))
            if material.category == primary.material.category and len(topic_words & candidate_words) >= 2:
                related.append(material)
        return [primary.material, *related[:2]]

    def run(self, mode: str, mock_generation: bool = False, mock_publish: bool = False) -> dict:
        if mode not in MODES:
            raise ValueError(f"Mode must be one of: {', '.join(sorted(MODES))}")
        if mode == "automatic" and not mock_publish and os.getenv("AUTOMATION_APPROVED", "").lower() != "true":
            raise RuntimeError("Automatic publishing is safety-gated. Set AUTOMATION_APPROVED=true only after readiness checks and sample approval.")
        try:
            collector = FeedCollector(self.config["request_timeout_seconds"], self.config["max_feed_items"])
            live = collector.collect(self.config["source_config"]["sources"], self.config["keywords"].get("required_any", []))
            candidate = self._select(live)
            if candidate is None:
                LOGGER.warning("No reliable, non-repeated millet topic is available; publication skipped")
                return {"status": "skipped", "reason": "no_eligible_topic"}
            generator = MockGenerator() if mock_generation else GeminiGenerator(timeout=45)
            materials = self._supporting(candidate, live)
            post = generator.generate(materials, candidate.normalized_topic)
            post.normalized_topic = candidate.normalized_topic
            post.category = candidate.material.category
            post.draft_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
            image_path = self.output / "images" / f"{post.draft_id}.jpg"
            post.image_path = str(self.renderer.generate(post, image_path))
            validation = self.validator.validate(post, materials)
            if not validation.valid:
                LOGGER.error("Generated post failed validation", extra={"errors": validation.errors})
                return {"status": "rejected", "errors": validation.errors}

            draft_path = self.output / "drafts" / f"{post.draft_id}.json"
            draft_path.parent.mkdir(parents=True, exist_ok=True)
            draft_payload = {"post": post.to_dict(), "materials": [item.to_dict() for item in materials], "validation": {"valid": True, "warnings": validation.warnings}}
            draft_path.write_text(json.dumps(draft_payload, ensure_ascii=False, indent=2), encoding="utf-8")
            status = "pending" if mode == "approval" else "dry_run"
            self.history.save_draft(post, candidate.material, status=status)
            if mode == "automatic":
                post_id = self._publish(post, mock_publish)
                self.history.set_status(post.draft_id, "published", post_id)
                status = "published"
            return {"status": status, "draft_id": post.draft_id, "draft_path": str(draft_path), "image_path": post.image_path}
        except Exception as exc:
            try:
                notify_failure(str(exc))
            except Exception:
                LOGGER.exception("Failure notification also failed")
            raise

    def _publish(self, post: GeneratedPost, mock: bool) -> str:
        if mock:
            return MockPublisher().publish("https://example.invalid/mock.jpg", post.caption + "\n\n" + " ".join(post.hashtags))
        image_url = GitHubImageHost().upload(post.image_path)
        return InstagramPublisher().publish(image_url, post.caption + "\n\n" + " ".join(post.hashtags))

    def approve(self, draft_id: str, mock_publish: bool = False) -> dict:
        row = self.history.get(draft_id)
        if row is None:
            raise KeyError(f"Draft not found: {draft_id}")
        if row["status"] != "pending":
            raise RuntimeError(f"Draft status is {row['status']!r}, not 'pending'")
        draft_path = self.output / "drafts" / f"{draft_id}.json"
        payload = json.loads(draft_path.read_text(encoding="utf-8"))
        post = GeneratedPost.from_dict(payload["post"])
        materials = [SourceMaterial(**m) for m in payload["materials"]]
        validation = self.validator.validate(post, materials)
        if not validation.valid:
            self.history.set_status(draft_id, "rejected", error="; ".join(validation.errors))
            return {"status": "rejected", "errors": validation.errors}
        post_id = self._publish(post, mock_publish)
        self.history.set_status(draft_id, "published", post_id)
        return {"status": "published", "draft_id": draft_id, "instagram_post_id": post_id}

    def publish_file(self, draft_path: str | Path, mock_publish: bool = False) -> dict:
        """Revalidate and publish an explicitly reviewed draft artifact."""
        target = Path(draft_path)
        payload = json.loads(target.read_text(encoding="utf-8"))
        post = GeneratedPost.from_dict(payload["post"])
        materials = [SourceMaterial(**material) for material in payload["materials"]]
        validation = self.validator.validate(post, materials)
        if not validation.valid:
            return {"status": "rejected", "errors": validation.errors}
        image_path = Path(post.image_path)
        if not image_path.is_absolute():
            image_path = Path(self.config["root"]) / image_path
        if not image_path.is_file():
            raise FileNotFoundError(f"Reviewed image does not exist: {image_path}")
        post.image_path = str(image_path)
        post_id = self._publish(post, mock_publish)
        existing = self.history.get(post.draft_id)
        if existing is None:
            self.history.save_draft(post, materials[0], status="pending")
        self.history.set_status(post.draft_id, "published", post_id)
        return {"status": "published", "draft_id": post.draft_id, "instagram_post_id": post_id}
