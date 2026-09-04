from __future__ import annotations

import json
from pathlib import Path

from .evergreen import load_evergreen
from .generator import MockGenerator
from .image import BrandedImageGenerator
from .relevance import normalize_topic
from .validation import PostValidator


SAMPLE_IDS = {"fao-millets-arid-lands", "iimr-eight-millets", "fao-millets-heritage"}


def generate_samples(config: dict) -> list[dict]:
    root = Path(config["root"])
    materials = [m for m in load_evergreen(root / "data/evergreen.yaml") if m.source_id in SAMPLE_IDS]
    generator = MockGenerator()
    renderer = BrandedImageGenerator(config["branding"])
    validator = PostValidator()
    results = []
    for index, material in enumerate(materials, 1):
        post = generator.generate([material], normalize_topic(material.title))
        post.draft_id = f"sample-{index}"
        image_path = root / "samples" / f"sample-{index}.jpg"
        post.image_path = str(renderer.generate(post, image_path))
        check = validator.validate(post, [material])
        if not check.valid:
            raise RuntimeError(f"Sample {index} failed validation: {check.errors}")
        payload = {"post": post.to_dict(), "materials": [material.to_dict()], "validation": {"valid": True}}
        json_path = root / "samples" / f"sample-{index}.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        results.append({"sample": index, "headline": post.headline, "caption": post.caption, "hashtags": post.hashtags, "image_path": str(image_path), "json_path": str(json_path)})
    (root / "samples" / "index.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    return results

