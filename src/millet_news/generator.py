from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from .http import retrying_session
from .models import Claim, GeneratedPost, SourceMaterial

SYSTEM_INSTRUCTION = """You are the editorial engine for an Instagram account exclusively about millet grains.
Use only the supplied source material. Do not add outside facts. Write original, concise English for a general
audience. Never claim prevention, cure, or treatment of disease. Distinguish human, animal, and laboratory
research. Every factual sentence in the headline, summary, caption, or image text must be represented in claims.
For each claim, provide short exact evidence excerpts and their matching source URLs. Significant numerical,
health, policy, market, or research claims should cite two independent sources when two are supplied. Do not
use clickbait. Include source name and publication date near the caption end. Output JSON only."""

SCHEMA: dict[str, Any] = {
    "type": "OBJECT",
    "required": ["headline", "summary", "caption", "category", "hashtags", "image_text", "claims", "sources", "normalized_topic"],
    "properties": {
        "headline": {"type": "STRING"},
        "summary": {"type": "STRING"},
        "caption": {"type": "STRING"},
        "category": {"type": "STRING"},
        "hashtags": {"type": "ARRAY", "items": {"type": "STRING"}},
        "image_text": {"type": "STRING"},
        "normalized_topic": {"type": "STRING"},
        "language": {"type": "STRING"},
        "claims": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["text", "source_urls", "evidence_quotes", "significant", "research_type"], "properties": {
            "text": {"type": "STRING"}, "source_urls": {"type": "ARRAY", "items": {"type": "STRING"}},
            "evidence_quotes": {"type": "ARRAY", "items": {"type": "STRING"}}, "significant": {"type": "BOOLEAN"},
            "research_type": {"type": "STRING"}
        }}},
        "sources": {"type": "ARRAY", "items": {"type": "OBJECT", "required": ["name", "url", "published_at"], "properties": {
            "name": {"type": "STRING"}, "url": {"type": "STRING"}, "published_at": {"type": "STRING"}
        }}},
    },
}


def _prompt(materials: list[SourceMaterial], topic: str) -> str:
    blocks = []
    for index, item in enumerate(materials, 1):
        blocks.append(
            f"SOURCE {index}\nName: {item.source_name}\nDate: {item.published_at}\nURL: {item.url}\n"
            f"Title: {item.title}\nRetrieved text:\n{item.text[:7000]}"
        )
    return (
        f"Create one millet-only Instagram post about this topic: {topic}. "
        "Use 5-10 controlled millet hashtags. Keep the full caption under 1,700 characters. "
        "Keep image_text under 150 characters.\n\n" + "\n\n".join(blocks)
    )


class GeminiGenerator:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 45) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self.timeout = timeout

    def generate(self, materials: list[SourceMaterial], topic: str) -> GeneratedPost:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for live generation; use --mock-generation only for tests/samples")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": _prompt(materials, topic)}]}],
            "generationConfig": {
                "temperature": 0.25,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        response = retrying_session(retry_post=True).post(url, params={"key": self.api_key}, json=body, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini returned no usable content: {payload}") from exc
        return GeneratedPost.from_dict(json.loads(text))


class MockGenerator:
    """Deterministic and source-bound. Never used implicitly in automatic mode."""

    def generate(self, materials: list[SourceMaterial], topic: str) -> GeneratedPost:
        item = materials[0]
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", item.text) if len(s.split()) >= 5]
        evidence = sentences[0] if sentences else item.text[:240]
        if len(sentences) > 1 and re.sub(r"\W+", " ", evidence).strip().lower() == re.sub(r"\W+", " ", item.title).strip().lower():
            evidence = sentences[1]
        fact = evidence.rstrip(".") + "."
        headline = item.title[:90]
        source_line = f"Source: {item.source_name} ({item.published_at[:10]})"
        caption = f"{headline}\n\n{fact}\n\nWhy it matters: this is a millet-specific fact worth understanding.\n\n{source_line}"
        return GeneratedPost(
            headline=headline,
            summary=fact,
            caption=caption,
            category=item.category,
            hashtags=["#Millets", "#MilletFacts", "#KnowYourMillets", "#IndianMillets"],
            image_text=fact[:145],
            claims=[
                Claim(text=headline, source_urls=[item.url], evidence_quotes=[item.title], significant=False),
                Claim(text=fact, source_urls=[item.url], evidence_quotes=[evidence], significant=False),
            ],
            sources=[{"name": item.source_name, "url": item.url, "published_at": item.published_at}],
            normalized_topic=topic,
        )
