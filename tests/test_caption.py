from millet_news.generator import MockGenerator
from millet_news.models import SourceMaterial


def test_caption_is_millet_only_attributed_and_controlled():
    item = SourceMaterial(
        "Foxtail millet is a distinct millet crop",
        "https://www.millets.res.in/",
        "ICAR–IIMR",
        "2024-02-03T00:00:00+00:00",
        "Foxtail millet is a distinct millet crop. Foxtail millet is cultivated as a food grain in parts of Asia.",
        category="varieties",
    )
    post = MockGenerator().generate([item], "foxtail-millet-profile")
    assert "Source: ICAR–IIMR (2024-02-03)" in post.caption
    assert 3 <= len(post.hashtags) <= 12
    assert all("millet" in tag.lower() for tag in post.hashtags)

