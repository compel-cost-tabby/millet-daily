from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class SourceMaterial:
    title: str
    url: str
    source_name: str
    published_at: str
    text: str
    credibility: float = 1.0
    country: str = "global"
    category: str = "news"
    source_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Candidate:
    material: SourceMaterial
    normalized_topic: str
    relevance_score: float
    rank_score: float = 0.0


@dataclass(slots=True)
class Claim:
    text: str
    source_urls: list[str]
    evidence_quotes: list[str]
    significant: bool = False
    research_type: str = "not_applicable"

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Claim":
        return cls(
            text=str(value.get("text", "")).strip(),
            source_urls=[str(v) for v in value.get("source_urls", [])],
            evidence_quotes=[str(v) for v in value.get("evidence_quotes", [])],
            significant=bool(value.get("significant", False)),
            research_type=str(value.get("research_type", "not_applicable")),
        )


@dataclass(slots=True)
class GeneratedPost:
    headline: str
    summary: str
    caption: str
    category: str
    hashtags: list[str]
    image_text: str
    claims: list[Claim]
    sources: list[dict[str, str]]
    normalized_topic: str
    language: str = "en"
    draft_id: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    image_path: str = ""

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GeneratedPost":
        required = ("headline", "summary", "caption", "category", "hashtags", "image_text", "claims", "sources", "normalized_topic")
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"Generated JSON is missing: {', '.join(missing)}")
        return cls(
            headline=str(value["headline"]).strip(),
            summary=str(value["summary"]).strip(),
            caption=str(value["caption"]).strip(),
            category=str(value["category"]).strip().lower(),
            hashtags=[str(v).strip() for v in value["hashtags"]],
            image_text=str(value["image_text"]).strip(),
            claims=[Claim.from_dict(v) for v in value["claims"]],
            sources=[dict(v) for v in value["sources"]],
            normalized_topic=str(value["normalized_topic"]).strip().lower(),
            language=str(value.get("language", "en")),
            draft_id=str(value.get("draft_id", "")),
            created_at=str(value.get("created_at", utc_now_iso())),
            image_path=str(value.get("image_path", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

