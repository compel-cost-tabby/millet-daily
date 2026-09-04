from __future__ import annotations

import math
import random
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import GeneratedPost

WIDTH, HEIGHT = 1080, 1350


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    windows = Path("C:/Windows/Fonts")
    choices = [windows / ("arialbd.ttf" if bold else "arial.ttf"), windows / ("segoeuib.ttf" if bold else "segoeui.ttf")]
    for path in choices:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def _rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _fit_lines(draw: ImageDraw.ImageDraw, text: str, max_width: int, max_lines: int, start_size: int, min_size: int = 34) -> tuple[ImageFont.ImageFont, list[str]]:
    for size in range(start_size, min_size - 1, -2):
        font = _font(size, bold=True)
        words = text.split()
        lines: list[str] = []
        current = ""
        for word in words:
            trial = f"{current} {word}".strip()
            if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
                current = trial
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if len(lines) <= max_lines:
            return font, lines
    return _font(min_size, bold=True), textwrap.wrap(text, width=28)[:max_lines]


class BrandedImageGenerator:
    def __init__(self, branding: dict) -> None:
        self.branding = branding
        self.palette = {key: _rgb(value) for key, value in branding["palette"].items()}

    def generate(self, post: GeneratedPost, output_path: str | Path) -> Path:
        target = Path(output_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        image = Image.new("RGB", (WIDTH, HEIGHT), self.palette["background"])
        draw = ImageDraw.Draw(image)

        # Original vector-like millet panicles: no third-party imagery.
        seed = sum(ord(ch) for ch in post.normalized_topic)
        rng = random.Random(seed)
        for origin_x in (80, 910):
            flip = 1 if origin_x < WIDTH // 2 else -1
            draw.line((origin_x, 1240, origin_x + 70 * flip, 780), fill=self.palette["accent"], width=12)
            for index in range(15):
                y = 820 + index * 25
                stem_x = origin_x + int((1240 - y) * 0.15 * flip)
                angle = (-1 if index % 2 else 1) * flip
                branch_x = stem_x + (55 + rng.randint(-10, 14)) * angle
                draw.line((stem_x, y, branch_x, y - 35), fill=self.palette["accent"], width=5)
                for grain in range(3):
                    gx = branch_x + grain * 13 * angle
                    gy = y - 40 - grain * 5
                    draw.ellipse((gx - 8, gy - 12, gx + 8, gy + 12), fill=self.palette["secondary"])

        draw.rounded_rectangle((58, 55, 1022, 1295), radius=36, outline=self.palette["primary"], width=4)
        draw.ellipse((90, 88, 205, 203), fill=self.palette["primary"])
        logo_font = _font(39, bold=True)
        logo = self.branding["logo_text"]
        box = draw.textbbox((0, 0), logo, font=logo_font)
        draw.text((147 - (box[2] - box[0]) / 2, 145 - (box[3] - box[1]) / 2 - box[1]), logo, font=logo_font, fill=self.palette["background"])
        draw.text((230, 100), self.branding["account_name"].upper(), font=_font(33, bold=True), fill=self.palette["primary"])
        draw.text((230, 148), post.category.upper(), font=_font(24, bold=True), fill=self.palette["accent"])

        draw.rounded_rectangle((105, 275, 975, 1010), radius=38, fill=(255, 253, 247))
        draw.rectangle((105, 275, 125, 1010), fill=self.palette["secondary"])
        headline_font, headline_lines = _fit_lines(draw, post.headline, 740, 4, 70, 44)
        y = 345
        for line in headline_lines:
            draw.text((170, y), line, font=headline_font, fill=self.palette["ink"])
            y += headline_font.size * 1.18
        y += 42
        body_font, body_lines = _fit_lines(draw, post.image_text, 720, 5, 42, 30)
        for line in body_lines:
            draw.text((170, y), line, font=body_font, fill=self.palette["muted"])
            y += body_font.size * 1.35

        draw.line((150, 1135, 930, 1135), fill=self.palette["secondary"], width=3)
        footer = self.branding["footer"]
        draw.text((150, 1175), footer, font=_font(24, bold=True), fill=self.palette["primary"])
        handle = self.branding.get("handle", "")
        hbox = draw.textbbox((0, 0), handle, font=_font(25))
        draw.text((930 - hbox[2], 1217), handle, font=_font(25), fill=self.palette["muted"])

        image.save(target, "JPEG", quality=92, optimize=True, dpi=(72, 72))
        return target

