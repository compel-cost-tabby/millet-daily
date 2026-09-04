from millet_news.generator import MockGenerator
from millet_news.models import SourceMaterial
from millet_news.relevance import normalize_topic
from millet_news.validation import PostValidator


def source() -> SourceMaterial:
    return SourceMaterial(
        "Pearl millet grows in drylands",
        "https://www.icrisat.org/crops/pearl-millet/",
        "ICRISAT",
        "2025-01-01T00:00:00+00:00",
        "Pearl millet grows in drylands. Pearl millet is cultivated in semi-arid regions of Africa and Asia.",
        category="farming",
    )


def test_source_bound_mock_post_passes():
    item = source()
    post = MockGenerator().generate([item], normalize_topic(item.title))
    assert PostValidator().validate(post, [item]).valid


def test_invented_evidence_and_health_claim_fail():
    item = source()
    post = MockGenerator().generate([item], normalize_topic(item.title))
    post.caption += " Millet cures diabetes."
    post.claims[0].evidence_quotes[0] = "This was never in the source"
    result = PostValidator().validate(post, [item])
    assert not result.valid
    assert any("Prohibited" in error for error in result.errors)
    assert any("not present" in error for error in result.errors)


def test_questions_and_hashtag_lines_are_not_factual_claims():
    item = source()
    post = MockGenerator().generate([item], normalize_topic(item.title))
    post.caption = post.caption.replace(
        "Why it matters: this is a millet-specific fact worth understanding.",
        "Why does pearl millet matter?\n\n#Millets #MilletFacts #IndianMillets",
    )
    assert PostValidator().validate(post, [item]).valid
