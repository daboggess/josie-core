"""
Deterministic social graphic compositor for Josie Creative Studio.
Uses HTML/CSS templates rendered via headless Chromium (Playwright).
"""

from __future__ import annotations

import base64
import html
import os
from pathlib import Path
import time
from typing import Any, Dict, Literal, Optional, Tuple

from playwright.sync_api import sync_playwright

AspectName = Literal["square", "portrait", "story"]

DIMENSIONS: dict[str, tuple[int, int]] = {
    "square": (1080, 1080),
    "portrait": (1080, 1350),
    "story": (1080, 1920),
}

DEFAULT_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates" / "social_promo_v1"


class SocialCompositor:
    """Renders pixel-perfect marketing graphics from text and background imagery."""

    def __init__(self, template_dir: Path | str | None = None) -> None:
        self.template_dir = Path(template_dir or DEFAULT_TEMPLATE_DIR)
        self.base_html_path = self.template_dir / "base.html"
        self.style_css_path = self.template_dir / "style.css"

        if not self.base_html_path.is_file():
            raise FileNotFoundError(f"Template base.html not found at: {self.base_html_path}")
        if not self.style_css_path.is_file():
            raise FileNotFoundError(f"Template style.css not found at: {self.style_css_path}")

        self._template_html = self.base_html_path.read_text(encoding="utf-8")
        self._style_css = self.style_css_path.read_text(encoding="utf-8")

    def _encode_image(self, image_path: Path | str) -> str:
        path = Path(image_path)
        if not path.is_file():
            raise FileNotFoundError(f"Background image not found: {path}")

        suffix = path.suffix.lower()
        mime = "image/png"
        if suffix in (".jpg", ".jpeg"):
            mime = "image/jpeg"
        elif suffix == ".webp":
            mime = "image/webp"

        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    def build_html(
        self,
        background_path: Path | str,
        headline: str,
        subheadline: str,
        cta: str | None = None,
        brand: str | None = None,
        aspect_ratio: AspectName = "square",
    ) -> str:
        """Build the complete, self-contained HTML document for rendering."""
        if aspect_ratio not in DIMENSIONS:
            raise ValueError(f"Unsupported aspect_ratio '{aspect_ratio}'. Must be one of {list(DIMENSIONS.keys())}")

        bg_src = self._encode_image(background_path)

        escaped_headline = html.escape(headline)
        escaped_subheadline = html.escape(subheadline)

        if brand:
            escaped_brand = html.escape(brand)
            brand_section = (
                '<div class="brand-wrapper">'
                '<div class="brand-badge">'
                '<span class="brand-icon"></span>'
                f'<span class="brand-name">{escaped_brand}</span>'
                '</div></div>'
            )
        else:
            brand_section = '<div class="brand-wrapper"></div>'

        if cta:
            escaped_cta = html.escape(cta)
            cta_section = (
                '<div class="cta-wrapper">'
                '<div class="cta-button">'
                f'<span>{escaped_cta}</span>'
                '<span class="cta-arrow">&rarr;</span>'
                '</div></div>'
            )
        else:
            cta_section = ""

        rendered = self._template_html
        rendered = rendered.replace("{{style_css}}", self._style_css)
        rendered = rendered.replace("{{aspect_ratio}}", aspect_ratio)
        rendered = rendered.replace("{{bg_image_src}}", bg_src)
        rendered = rendered.replace("{{headline}}", escaped_headline)
        rendered = rendered.replace("{{subheadline}}", escaped_subheadline)
        rendered = rendered.replace("{{brand_section}}", brand_section)
        rendered = rendered.replace("{{cta_section}}", cta_section)

        return rendered

    def render_asset(
        self,
        background_path: Path | str,
        headline: str,
        subheadline: str,
        cta: str | None = None,
        brand: str | None = None,
        aspect_ratio: AspectName = "square",
        output_path: Path | str | None = None,
    ) -> dict[str, Any]:
        """Render a single graphic at the specified aspect ratio."""
        width, height = DIMENSIONS[aspect_ratio]

        if output_path is None:
            raise ValueError("output_path must be provided.")
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)

        content = self.build_html(
            background_path=background_path,
            headline=headline,
            subheadline=subheadline,
            cta=cta,
            brand=brand,
            aspect_ratio=aspect_ratio,
        )

        t0 = time.time()
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.set_viewport_size({"width": width, "height": height})
            page.set_content(content, wait_until="load")
            page.screenshot(path=str(dest), type="png")
            browser.close()
        elapsed = time.time() - t0

        return {
            "aspect_ratio": aspect_ratio,
            "path": str(dest.resolve()),
            "width": width,
            "height": height,
            "file_size": dest.stat().st_size,
            "render_time_seconds": round(elapsed, 3),
        }

    def render_package(
        self,
        background_path: Path | str,
        headline: str,
        subheadline: str,
        cta: str | None = None,
        brand: str | None = None,
        output_dir: Path | str | None = None,
    ) -> dict[str, Any]:
        """Render the complete social graphic package (square, portrait, story) in a single browser session."""
        if output_dir is None:
            raise ValueError("output_dir must be provided.")
        dest_dir = Path(output_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        results: dict[str, Any] = {}
        total_t0 = time.time()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()

            for aspect_ratio, (width, height) in DIMENSIONS.items():
                content = self.build_html(
                    background_path=background_path,
                    headline=headline,
                    subheadline=subheadline,
                    cta=cta,
                    brand=brand,
                    aspect_ratio=aspect_ratio,  # type: ignore
                )
                output_file = dest_dir / f"{aspect_ratio}.png"

                t0 = time.time()
                page.set_viewport_size({"width": width, "height": height})
                page.set_content(content, wait_until="load")
                page.screenshot(path=str(output_file), type="png")
                elapsed = time.time() - t0

                results[aspect_ratio] = {
                    "path": str(output_file.resolve()),
                    "width": width,
                    "height": height,
                    "file_size": output_file.stat().st_size,
                    "render_time_seconds": round(elapsed, 3),
                }

            browser.close()

        total_elapsed = time.time() - total_t0
        return {
            "status": "PASS",
            "assets": results,
            "total_render_time_seconds": round(total_elapsed, 3),
        }


def render_social_package(
    background_path: Path | str,
    headline: str,
    subheadline: str,
    cta: str | None = None,
    brand: str | None = None,
    output_dir: Path | str | None = None,
) -> dict[str, Any]:
    """Top-level convenience function to generate the 3-asset social package."""
    compositor = SocialCompositor()
    return compositor.render_package(
        background_path=background_path,
        headline=headline,
        subheadline=subheadline,
        cta=cta,
        brand=brand,
        output_dir=output_dir,
    )
