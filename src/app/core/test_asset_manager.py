import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from src.app.core.asset_manager import build_asset_paths, build_vditor_upload_response, save_image_asset


class TestDiaryAssetManager(unittest.TestCase):
    def test_builds_dated_asset_paths_for_diary_source(self):
        paths = build_asset_paths(
            source_path="diary/0526.md",
            original_filename="screenshot.png",
            now=datetime(2026, 5, 26, 15, 30, 12),
        )

        self.assertEqual(
            paths.asset_path,
            "assets/diary/2026-05-26/20260526-153012-screenshot.png",
        )
        self.assertEqual(
            paths.markdown_path,
            "../assets/diary/2026-05-26/20260526-153012-screenshot.png",
        )
        self.assertEqual(
            paths.static_path,
            "/assets/diary/2026-05-26/20260526-153012-screenshot.png",
        )

    def test_builds_paths_for_legacy_non_padded_diary_filename(self):
        paths = build_asset_paths(
            source_path="diary/526.md",
            original_filename="diagram with spaces.webp",
            now=datetime(2026, 5, 26, 8, 1, 2),
        )

        self.assertEqual(
            paths.asset_path,
            "assets/diary/2026-05-26/20260526-080102-diagram-with-spaces.webp",
        )
        self.assertEqual(
            paths.markdown_path,
            "../assets/diary/2026-05-26/20260526-080102-diagram-with-spaces.webp",
        )

    def test_rejects_path_traversal_source_paths(self):
        with self.assertRaises(ValueError):
            build_asset_paths(
                source_path="../secrets.md",
                original_filename="screenshot.png",
                now=datetime(2026, 5, 26, 15, 30, 12),
            )

    def test_builds_source_scoped_asset_paths_for_ideas_source(self):
        paths = build_asset_paths(
            source_path="ideas/DeepMemo.md",
            original_filename="architecture.png",
            now=datetime(2026, 5, 26, 16, 2, 3),
        )

        self.assertEqual(
            paths.asset_path,
            "assets/ideas/DeepMemo/20260526-160203-architecture.png",
        )
        self.assertEqual(
            paths.markdown_path,
            "../assets/ideas/DeepMemo/20260526-160203-architecture.png",
        )
        self.assertEqual(
            paths.static_path,
            "/assets/ideas/DeepMemo/20260526-160203-architecture.png",
        )

    def test_vditor_response_maps_original_name_to_markdown_path(self):
        response = build_vditor_upload_response(
            original_filename="screenshot.png",
            markdown_path="../assets/diary/2026-05-26/20260526-153012-screenshot.png",
        )

        self.assertEqual(response["code"], 0)
        self.assertEqual(response["data"]["errFiles"], [])
        self.assertEqual(
            response["data"]["succMap"],
            {
                "screenshot.png": "../assets/diary/2026-05-26/20260526-153012-screenshot.png",
            },
        )

    def test_saves_image_asset_under_data_assets(self):
        with TemporaryDirectory() as tmp_dir:
            result = save_image_asset(
                data_dir=Path(tmp_dir),
                source_path="diary/0526.md",
                original_filename="screenshot.png",
                content_type="image/png",
                content=b"png-bytes",
                now=datetime(2026, 5, 26, 15, 30, 12),
            )

            stored = Path(tmp_dir) / "assets/diary/2026-05-26/20260526-153012-screenshot.png"
            self.assertEqual(stored.read_bytes(), b"png-bytes")
            self.assertEqual(result["asset_path"], "assets/diary/2026-05-26/20260526-153012-screenshot.png")
            self.assertEqual(
                result["markdown_path"],
                "../assets/diary/2026-05-26/20260526-153012-screenshot.png",
            )
            self.assertEqual(result["static_path"], "/assets/diary/2026-05-26/20260526-153012-screenshot.png")

    def test_rejects_non_image_uploads(self):
        with TemporaryDirectory() as tmp_dir:
            with self.assertRaises(ValueError):
                save_image_asset(
                    data_dir=Path(tmp_dir),
                    source_path="diary/0526.md",
                    original_filename="notes.txt",
                    content_type="text/plain",
                    content=b"not an image",
                    now=datetime(2026, 5, 26, 15, 30, 12),
                )


if __name__ == "__main__":
    unittest.main()
