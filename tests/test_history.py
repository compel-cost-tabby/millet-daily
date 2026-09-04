from millet_news.history import HistoryStore
from millet_news.models import GeneratedPost, SourceMaterial


def test_duplicate_url_and_topic_are_remembered(tmp_path):
    store = HistoryStore(tmp_path / "history.db")
    post = GeneratedPost("Millet fact", "Fact.", "Millet fact.", "history", ["#Millets", "#MilletFacts", "#Ragi"], "Fact.", [], [], "millet-fact", draft_id="one")
    source = SourceMaterial("Millet fact", "https://www.fao.org/fact", "FAO", "2026-01-01T00:00:00+00:00", "Millet fact.")
    store.save_draft(post, source)
    assert store.seen_url(source.url)
    assert store.topic_recent("millet-fact", 90)

