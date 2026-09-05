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
For each claim, provide short exact evidence excerpts and their matching source URLs. The source_urls and
evidence_quotes arrays must have identical lengths, with each evidence quote paired to the URL at the same index.
Significant numerical, health, policy, market, or research claims should cite two independent sources when two
are supplied; otherwise set significant to false. Do not use clickbait or questions. Do not put hashtags in the
caption. Output JSON only."""

ALLOWED_HASHTAGS = (
    "#millet", "#millets", "#milletfacts", "#knowyourmillets", "#indianmillets", "#milletnews",
    "#milletnutrition", "#milletfarming", "#milletresearch", "#milletrecipes", "#milletsustainability",
    "#milletpolicy", "#jowar", "#bajra", "#ragi", "#sorghum", "#pearlmillet", "#fingermillet",
    "#foxtailmillet", "#littlemillet", "#kodomillet", "#barnyardmillet", "#prosomillet", "#browntopmillet",
)
DEFAULT_HASHTAGS = ("#millets", "#milletfacts", "#knowyourmillets", "#milletnews", "#indianmillets")

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
        "Use 5-10 hashtags selected verbatim only from this list: "
        f"{', '.join(ALLOWED_HASHTAGS)}. Do not put hashtags inside the caption. "
        "Keep the full caption under 1,700 characters and image_text under 150 characters. "
        "Do not write questions or calls to action. Every non-source sentence in headline, summary, caption, "
        "and image_text must have a corresponding claim whose text closely matches that sentence. For every "
        "claim, provide exactly one evidence quote for each source URL, in the same order. Evidence quotes must "
        "be exact contiguous excerpts from the retrieved text. Do not invent a source footer; the application "
        "adds the canonical source names and dates.\n\n" + "\n\n".join(blocks)
    )


def _normalize_post(post: GeneratedPost, materials: list[SourceMaterial], topic: str) -> GeneratedPost:
    """Apply deterministic output formatting without changing any factual claim."""
    allowed = set(ALLOWED_HASHTAGS)
    hashtags: list[str] = []
    for hashtag in post.hashtags:
        normalized = hashtag.strip().lower()
        if normalized in allowed and normalized not in hashtags:
            hashtags.append(normalized)
    for fallback in DEFAULT_HASHTAGS:
        if len(hashtags) >= 5:
            break
        if fallback not in hashtags:
            hashtags.append(fallback)
    post.hashtags = hashtags[:10]

    # Hashtags are appended by the publisher, so remove model-added copies from the caption.
    clean_lines = []
    for line in post.caption.splitlines():
        stripped = line.strip()
        if stripped.lower().startswith(("source:", "sources:")):
            continue
        stripped = re.sub(r"(?<!\w)#[A-Za-z0-9_]+", "", stripped).strip()
        if stripped:
            clean_lines.append(stripped)

    post.sources = [
        {"name": item.source_name, "url": item.url, "published_at": item.published_at}
        for item in materials
    ]
    allowed_research_types = {"not_applicable", "human", "animal", "laboratory", "review", "observational"}
    for claim in post.claims:
        research_type = re.sub(r"[^a-z]+", "_", claim.research_type.lower()).strip("_")
        claim.research_type = research_type if research_type in allowed_research_types else "not_applicable"

        # Pair every quote with the supplied source that actually contains it.
        grounded_pairs: list[tuple[str, str]] = []
        for quote in claim.evidence_quotes:
            normalized_quote = re.sub(r"\s+", " ", quote).strip().lower()
            for item in materials:
                normalized_text = re.sub(r"\s+", " ", item.text).lower()
                if normalized_quote and normalized_quote in normalized_text:
                    grounded_pairs.append((item.url, quote))
                    break
        if grounded_pairs:
            claim.source_urls = [url for url, _ in grounded_pairs]
            claim.evidence_quotes = [quote for _, quote in grounded_pairs]

    source_footer = "Sources: " + "; ".join(
        f"{item.source_name} ({item.published_at[:10]})" for item in materials
    )
    post.caption = "\n\n".join(clean_lines).strip() + f"\n\n{source_footer}"
    post.category = materials[0].category
    post.normalized_topic = topic
    return post


class GeminiGenerator:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: int = 45) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model = model or os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
        configured_fallbacks = os.getenv(
            "GEMINI_FALLBACK_MODELS", "gemini-3.1-flash-lite,gemini-2.5-flash-lite"
        )
        self.models = list(dict.fromkeys([
            self.model,
            *(value.strip() for value in configured_fallbacks.split(",") if value.strip()),
        ]))
        self.timeout = timeout

    def _request(self, prompt: str) -> GeneratedPost:
        body = {
            "systemInstruction": {"parts": [{"text": SYSTEM_INSTRUCTION}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.15,
                "responseMimeType": "application/json",
                "responseSchema": SCHEMA,
            },
        }
        response = None
        last_error: requests.RequestException | None = None
        for index, model_name in enumerate(self.models):
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                response = retrying_session(total=2, retry_post=True, backoff_factor=5).post(
                    url, headers={"x-goog-api-key": self.api_key}, json=body, timeout=self.timeout
                )
                response.raise_for_status()
                break
            except requests.RequestException as exc:
                last_error = exc
                status = exc.response.status_code if exc.response is not None else None
                retry_exhausted = isinstance(exc, requests.exceptions.RetryError)
                if index == len(self.models) - 1 or (not retry_exhausted and status not in {429, 500, 503, 504}):
                    raise
        if response is None or not response.ok:
            assert last_error is not None
            raise last_error
        payload = response.json()
        try:
            text = payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as exc:
            raise RuntimeError(f"Gemini returned no usable content: {payload}") from exc
        return GeneratedPost.from_dict(json.loads(text))

    def generate(self, materials: list[SourceMaterial], topic: str) -> GeneratedPost:
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is required for live generation; use --mock-generation only for tests/samples")
        prompt = _prompt(materials, topic)
        post = _normalize_post(self._request(prompt), materials, topic)

        # Give Gemini one bounded repair attempt. The normal validator remains the final safety gate.
        from .validation import PostValidator

        validation = PostValidator().validate(post, materials)
        if validation.valid:
            return post
        repair_prompt = (
            prompt
            + "\n\nYour first JSON draft failed validation. Return a complete corrected JSON object only. "
            + "Fix every issue without adding facts or changing the supplied evidence. Validation issues:\n- "
            + "\n- ".join(validation.errors)
            + "\n\nFirst draft:\n"
            + json.dumps(post.to_dict(), ensure_ascii=False)
        )
        return _normalize_post(self._request(repair_prompt), materials, topic)


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
