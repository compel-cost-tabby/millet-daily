from PIL import Image

from millet_news.generator import MockGenerator
from millet_news.image import BrandedImageGenerator
from millet_news.models import SourceMaterial


def test_image_is_correct_size_and_jpeg(tmp_path):
    branding = {"account_name": "Millet Daily", "handle": "@milletdaily", "logo_text": "MD", "footer": "MILLET • EVIDENCE • EVERY DAY", "palette": {"background": "#FFF8E8", "primary": "#6B4F2A", "secondary": "#D49A35", "accent": "#587A4A", "ink": "#232018", "muted": "#746B5D"}}
    source = SourceMaterial("Ragi is finger millet", "https://example.org/ragi", "Source", "2024-01-01T00:00:00+00:00", "Ragi is finger millet. Ragi is a common name for finger millet in India.", category="varieties")
    post = MockGenerator().generate([source], "ragi-finger-millet")
    output = BrandedImageGenerator(branding).generate(post, tmp_path / "post.jpg")
    with Image.open(output) as image:
        assert image.size == (1080, 1350)
        assert image.format == "JPEG"

