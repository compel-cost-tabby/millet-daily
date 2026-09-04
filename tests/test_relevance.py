from millet_news.models import SourceMaterial
from millet_news.relevance import filter_and_rank, normalize_topic, score_relevance


KEYWORDS = {"strong_terms": ["millet", "millets", "ragi", "bajra"], "incidental_context": ["including millet"]}


def material(title: str, text: str) -> SourceMaterial:
    return SourceMaterial(title, "https://www.fao.org/item", "FAO", "2026-09-01T00:00:00+00:00", text)


def test_rejects_incidental_mention():
    item = material("New programme for crops", "The programme covers rice, wheat, maize, pulses and other grains including millet.")
    assert score_relevance(item, KEYWORDS) < 0.5


def test_accepts_millet_central_story_and_normalizes_topic():
    item = material("Ragi millet farming expands", "Ragi millet farmers are testing new millet seed lines for dryland cultivation and harvest.")
    ranked = filter_and_rank([item], KEYWORDS, {"farming": 1.0})
    assert ranked and ranked[0].material.category == "farming"
    assert normalize_topic("New Ragi Millet Study in India") == "millet-ragi"

