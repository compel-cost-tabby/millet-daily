from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone

from .models import Candidate, SourceMaterial

GENERIC_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "in", "is",
    "it", "new", "of", "on", "or", "the", "to", "with", "study", "news", "india",
}
CATEGORIES = {
    "nutrition": {"nutrition", "nutrient", "protein", "fiber", "iron", "calcium", "diet"},
    "farming": {"farm", "farmer", "cultivation", "crop", "yield", "seed", "harvest"},
    "sustainability": {"climate", "resilient", "drought", "water", "sustainable"},
    "recipes": {"recipe", "cook", "porridge", "roti", "storage", "soak"},
    "research": {"research", "study", "trial", "genome", "journal"},
    "industry": {"market", "price", "producer", "export", "industry"},
    "history": {"history", "ancient", "traditional", "heritage"},
    "varieties": {"variety", "jowar", "bajra", "ragi", "foxtail", "kodo", "proso", "barnyard"},
    "comparison": {"compare", "comparison", "rice", "wheat"},
    "myths": {"myth", "fact", "misconception"},
    "news": {"policy", "government", "initiative", "announced", "launch"},
}


def normalize_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).lower()
    value = re.sub(r"[^\w\s-]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_topic(title: str) -> str:
    words = [w for w in normalize_text(title).split() if w not in GENERIC_WORDS and len(w) > 2]
    return "-".join(sorted(dict.fromkeys(words))[:12])


def classify(text: str) -> str:
    words = set(normalize_text(text).split())
    scores = {name: len(words & terms) for name, terms in CATEGORIES.items()}
    return max(scores, key=scores.get) if max(scores.values(), default=0) else "news"


def score_relevance(material: SourceMaterial, keywords: dict) -> float:
    title = normalize_text(material.title)
    text = normalize_text(material.text)
    strong = [normalize_text(k) for k in keywords.get("strong_terms", [])]
    title_hits = sum(1 for term in strong if term and term in title)
    body_hits = sum(1 for term in strong if term and term in text)
    incidental = any(normalize_text(p) in text for p in keywords.get("incidental_context", []))
    if title_hits == 0 and body_hits < 2:
        return 0.0
    score = min(1.0, title_hits * 0.45 + body_hits * 0.16 + material.credibility * 0.2)
    if incidental and title_hits == 0:
        score *= 0.35
    return round(score, 4)


def filter_and_rank(materials: list[SourceMaterial], keywords: dict, category_weights: dict) -> list[Candidate]:
    now = datetime.now(timezone.utc)
    candidates: list[Candidate] = []
    for material in materials:
        relevance = score_relevance(material, keywords)
        if relevance < 0.5:
            continue
        if material.category == "news":
            material.category = classify(material.title + " " + material.text)
        try:
            age_days = max(0.0, (now - datetime.fromisoformat(material.published_at.replace("Z", "+00:00"))).total_seconds() / 86400)
        except ValueError:
            age_days = 30
        recency = max(0.0, 1.0 - min(age_days, 30) / 30)
        breaking_bonus = 0.12 if age_days <= 1 else 0.0
        recent_bonus = 0.08 if age_days <= 7 else 0.0
        india = 0.12 if material.country.lower() == "india" else 0.0
        education = 0.1 if len(material.text.split()) >= 25 else 0.03
        weight = float(category_weights.get(material.category, 1.0))
        rank = (relevance * 0.5 + material.credibility * 0.2 + recency * 0.18 + breaking_bonus + recent_bonus + education + india) * weight
        candidates.append(Candidate(material, normalize_topic(material.title), relevance, round(rank, 4)))
    return sorted(candidates, key=lambda item: item.rank_score, reverse=True)
