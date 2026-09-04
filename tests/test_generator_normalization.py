from millet_news.generator import ALLOWED_HASHTAGS, _normalize_post
from millet_news.generator import MockGenerator
from millet_news.models import SourceMaterial
from millet_news.relevance import normalize_topic


def test_normalization_controls_hashtags_and_source_footer():
    item = SourceMaterial(
        "Pearl millet grows in drylands",
        "https://www.icrisat.org/crops/pearl-millet/",
        "ICRISAT",
        "2025-01-01T00:00:00+00:00",
        "Pearl millet grows in drylands. Pearl millet is cultivated in semi-arid regions of Africa and Asia.",
        category="farming",
    )
    topic = normalize_topic(item.title)
    post = MockGenerator().generate([item], topic)
    post.hashtags = ["#Millets", "#SustainableAgriculture", "#MilletFacts"]
    post.caption += "\n\n#Millets #SustainableAgriculture\nSources: Incorrect (1900-01-01)"

    normalized = _normalize_post(post, [item], topic)

    assert len(normalized.hashtags) >= 5
    assert set(normalized.hashtags) <= set(ALLOWED_HASHTAGS)
    assert "#" not in normalized.caption
    assert normalized.caption.endswith("Sources: ICRISAT (2025-01-01)")
