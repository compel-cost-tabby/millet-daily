from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

from .models import GeneratedPost, SourceMaterial

ALLOWED_CATEGORIES = {"news", "nutrition", "varieties", "farming", "sustainability", "history", "recipes", "research", "comparison", "myths", "industry"}
BANNED_HEALTH = re.compile(r"\b(cures?|treats?|prevents?|heals?|reverses?|guarantees?|miracle)\b", re.I)
HEALTH_CONTEXT = re.compile(r"\b(health|diabetes|cholesterol|blood sugar|heart|disease|digestion|gut)\b", re.I)
UNCHECKED_SUPPORT = re.compile(r"(?<!may )\bsupports?\b", re.I)
NUMERIC = re.compile(r"\b\d+(?:[.,]\d+)?%?\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", value.lower())).strip()


def _words(value: str) -> set[str]:
    return {w for w in _norm(value).split() if len(w) > 2}


@dataclass(slots=True)
class ValidationResult:
    valid: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class PostValidator:
    def validate(self, post: GeneratedPost, materials: list[SourceMaterial]) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        by_url = {m.url: m for m in materials}
        allowed_urls = set(by_url)

        if not post.headline or len(post.headline) > 100:
            errors.append("Headline must be 1-100 characters")
        if len(post.caption) > 2200:
            errors.append("Caption exceeds Instagram's 2,200-character limit")
        if post.category not in ALLOWED_CATEGORIES:
            errors.append(f"Unsupported category: {post.category}")
        millet_terms = {"millet", "millets", "sorghum", "jowar", "bajra", "ragi", "foxtail", "kodo", "barnyard", "proso", "browntop"}
        if not post.normalized_topic or not (millet_terms & _words(" ".join([post.headline, post.summary, post.caption]))):
            errors.append("Post is not demonstrably millet-focused")
        if BANNED_HEALTH.search(" ".join([post.headline, post.summary, post.caption, post.image_text])):
            errors.append("Prohibited disease/health claim language detected")
        for sentence in SENTENCE.split(" ".join([post.headline, post.summary, post.caption, post.image_text])):
            if HEALTH_CONTEXT.search(sentence) and UNCHECKED_SUPPORT.search(sentence):
                errors.append("Health-support wording must be cautious (for example, 'may support')")
        if not 3 <= len(post.hashtags) <= 12 or any(not h.startswith("#") for h in post.hashtags):
            errors.append("Use 3-12 valid hashtags")
        if len(set(h.lower() for h in post.hashtags)) != len(post.hashtags):
            errors.append("Hashtags contain duplicates")
        allowed_hashtags = {
            "#millet", "#millets", "#milletfacts", "#knowyourmillets", "#indianmillets", "#milletnews",
            "#milletnutrition", "#milletfarming", "#milletresearch", "#milletrecipes", "#milletsustainability",
            "#milletpolicy", "#jowar", "#bajra", "#ragi", "#sorghum", "#pearlmillet", "#fingermillet",
            "#foxtailmillet", "#littlemillet", "#kodomillet", "#barnyardmillet", "#prosomillet", "#browntopmillet",
        }
        if any(h.lower() not in allowed_hashtags for h in post.hashtags):
            errors.append("Hashtag is outside the controlled millet-only set")

        comparison_words = re.compile(r"\b(more|less|higher|lower|versus|vs\.?|compared with|compared to)\b", re.I)
        basis_words = re.compile(r"\b(per\s+\d+\s*g|same serving|both cooked|both raw|cooked basis|raw basis)\b", re.I)
        if post.category in {"nutrition", "comparison"} and comparison_words.search(post.caption) and not basis_words.search(post.caption):
            errors.append("Nutrition comparison lacks an equivalent serving size and raw/cooked basis")

        source_urls = {str(s.get("url", "")) for s in post.sources}
        if not source_urls or not source_urls <= allowed_urls:
            errors.append("Attribution includes an unknown or missing source URL")
        for source in post.sources:
            if not source.get("name") or not source.get("published_at"):
                errors.append("Each source needs name and publication date")
            tail = post.caption[-700:].lower()
            if str(source.get("name", "")).lower() not in tail or str(source.get("published_at", ""))[:10] not in tail:
                errors.append("Caption ending must include each source name and publication date")

        if not post.claims:
            errors.append("No traceable claims were returned")
        for index, claim in enumerate(post.claims, 1):
            if not claim.text or not claim.source_urls or not claim.evidence_quotes:
                errors.append(f"Claim {index} lacks text, source URL, or evidence")
                continue
            if len(claim.source_urls) != len(claim.evidence_quotes):
                errors.append(f"Claim {index} must pair each source URL with one evidence excerpt")
                continue
            if claim.significant and len(set(claim.source_urls)) < 2 and len(materials) > 1:
                errors.append(f"Significant claim {index} is not corroborated by two supplied sources")
            if claim.research_type not in {"not_applicable", "human", "animal", "laboratory", "review", "observational"}:
                errors.append(f"Claim {index} has an invalid research type")
            if claim.research_type != "not_applicable" and claim.research_type not in " ".join([post.summary, post.caption]).lower():
                errors.append(f"Claim {index} does not clearly state its {claim.research_type} research type")
            for url, quote in zip(claim.source_urls, claim.evidence_quotes):
                if url not in allowed_urls:
                    errors.append(f"Claim {index} cites an unknown URL")
                    continue
                if _norm(quote) not in _norm(by_url[url].text):
                    errors.append(f"Claim {index} evidence is not present in retrieved source text")
                for number in NUMERIC.findall(claim.text):
                    if number not in quote:
                        errors.append(f"Claim {index} number {number} is absent from its evidence")
            if len(_words(claim.text) & set().union(*(_words(q) for q in claim.evidence_quotes))) < 3:
                errors.append(f"Claim {index} is not sufficiently grounded in its evidence")

        factual_sentences = []
        for block in (post.headline, post.summary, post.image_text, post.caption):
            for value in SENTENCE.split(block):
                value = value.strip()
                if len(_words(value)) >= 4 and not value.lower().startswith(("source:", "sources:", "why it matters:")):
                    factual_sentences.append(value)
        claim_words = [_words(c.text) for c in post.claims]
        for sentence in factual_sentences:
            words = _words(sentence)
            if not any(len(words & cw) / max(1, min(len(words), len(cw))) >= 0.45 for cw in claim_words):
                errors.append(f"Factual sentence is not represented in claims: {sentence[:80]}")

        for url in source_urls:
            host = urlparse(url).hostname
            if not host:
                errors.append(f"Invalid source URL: {url}")
        return ValidationResult(not errors, list(dict.fromkeys(errors)), warnings)
