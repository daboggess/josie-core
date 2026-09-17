import os
from pathlib import Path
import struct
import tempfile
import unittest

from creative_studio.engine.composer import (
    DIMENSIONS,
    SocialCompositor,
    render_social_package,
)

QUALIFICATION_IMAGE = Path(r"D:\Josie\creative_studio\qualification\image_engine_test.png")


def get_png_dimensions(path: Path | str) -> tuple[int, int]:
    """Extract width and height directly from PNG IHDR chunk (bytes 16-24)."""
    with open(path, "rb") as f:
        header = f.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"File {path} is not a valid PNG")
    return struct.unpack(">II", header[16:24])


class TestSocialCompositor(unittest.TestCase):
    """Deterministic qualification tests for the social graphic compositor."""

    def setUp(self) -> None:
        self.compositor = SocialCompositor()
        self.assertTrue(QUALIFICATION_IMAGE.is_file(), f"Qualification image missing: {QUALIFICATION_IMAGE}")

    def test_01_compositor_import(self) -> None:
        """Verify compositor module and functions import correctly."""
        self.assertIsNotNone(SocialCompositor)
        self.assertIsNotNone(render_social_package)
        self.assertEqual(set(DIMENSIONS.keys()), {"square", "portrait", "story"})
        self.assertEqual(DIMENSIONS["square"], (1080, 1080))
        self.assertEqual(DIMENSIONS["portrait"], (1080, 1350))
        self.assertEqual(DIMENSIONS["story"], (1080, 1920))

    def test_02_supplied_text_inserted_into_template(self) -> None:
        """Verify supplied text is correctly injected into rendered HTML before screenshot."""
        headline = "Custom Distinctive Headline 123"
        subheadline = "Detailed explanatory subhead for social promotion"
        cta = "CLAIM OFFER NOW"
        brand = "Test Brand Agency"

        html_out = self.compositor.build_html(
            background_path=QUALIFICATION_IMAGE,
            headline=headline,
            subheadline=subheadline,
            cta=cta,
            brand=brand,
            aspect_ratio="square",
        )

        self.assertIn(headline, html_out)
        self.assertIn(subheadline, html_out)
        self.assertIn(cta, html_out)
        self.assertIn(brand, html_out)
        self.assertIn("data:image/png;base64,", html_out)

    def test_03_no_external_http_resources(self) -> None:
        """Verify rendered HTML requires zero external HTTP/HTTPS network dependencies."""
        html_out = self.compositor.build_html(
            background_path=QUALIFICATION_IMAGE,
            headline="Offline Render Test",
            subheadline="Testing that no external CDN requests are made",
            cta="OFFLINE CTA",
            brand="Offline Brand",
            aspect_ratio="square",
        )

        self.assertNotIn("http://", html_out)
        self.assertNotIn("https://", html_out)

    def test_04_missing_background_path_fails_clearly(self) -> None:
        """Verify invalid or missing background path raises FileNotFoundError."""
        nonexistent = Path(r"D:\Josie\creative_studio\nonexistent_background_xyz.png")
        with self.assertRaises(FileNotFoundError):
            self.compositor.build_html(
                background_path=nonexistent,
                headline="Test",
                subheadline="Test",
                aspect_ratio="square",
            )

        with self.assertRaises(FileNotFoundError):
            self.compositor.render_asset(
                background_path=nonexistent,
                headline="Test",
                subheadline="Test",
                aspect_ratio="square",
                output_path=Path(tempfile.gettempdir()) / "test.png",
            )

    def test_05_all_three_output_files_created_with_exact_dimensions(self) -> None:
        """Verify square, portrait, and story assets render at exact pixel dimensions."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            out_dir = Path(tmp_dir)
            result = render_social_package(
                background_path=QUALIFICATION_IMAGE,
                headline="Make Something Worth Stopping For",
                subheadline="Local AI-powered creative production built on the Josie Box.",
                cta="CREATE WITH JOSIE",
                brand="Josie Creative Studio",
                output_dir=out_dir,
            )

            self.assertEqual(result["status"], "PASS")
            self.assertIn("assets", result)

            square_path = out_dir / "square.png"
            portrait_path = out_dir / "portrait.png"
            story_path = out_dir / "story.png"

            self.assertTrue(square_path.is_file(), f"Missing {square_path}")
            self.assertTrue(portrait_path.is_file(), f"Missing {portrait_path}")
            self.assertTrue(story_path.is_file(), f"Missing {story_path}")

            self.assertGreater(square_path.stat().st_size, 100_000)
            self.assertGreater(portrait_path.stat().st_size, 100_000)
            self.assertGreater(story_path.stat().st_size, 100_000)

            self.assertEqual(get_png_dimensions(square_path), (1080, 1080))
            self.assertEqual(get_png_dimensions(portrait_path), (1080, 1350))
            self.assertEqual(get_png_dimensions(story_path), (1080, 1920))


if __name__ == "__main__":
    unittest.main()
