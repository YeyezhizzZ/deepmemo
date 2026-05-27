import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import src.app.core.fs_manager as fs_manager


class TestFsManagerTree(unittest.TestCase):
    def test_scan_directory_tree_skips_non_markdown_files(self):
        with TemporaryDirectory() as tmp_dir:
            data_dir = Path(tmp_dir)
            (data_dir / "diary").mkdir()
            (data_dir / "diary/0526.md").write_text("# diary", encoding="utf-8")
            (data_dir / "assets/diary/2026-05-26").mkdir(parents=True)
            (data_dir / "assets/diary/2026-05-26/screenshot.png").write_bytes(b"png")

            original_data_dir = fs_manager.DATA_DIR
            original_get_file_meta = fs_manager.get_file_meta
            fs_manager.DATA_DIR = data_dir
            fs_manager.get_file_meta = lambda _path: None
            try:
                tree = fs_manager.scan_directory_tree()
            finally:
                fs_manager.DATA_DIR = original_data_dir
                fs_manager.get_file_meta = original_get_file_meta

            paths = self._flatten_paths(tree)
            self.assertIn("diary/0526.md", paths)
            self.assertIn("assets/diary/2026-05-26", paths)
            self.assertNotIn("assets/diary/2026-05-26/screenshot.png", paths)

    def _flatten_paths(self, nodes):
        paths = []
        for node in nodes:
            paths.append(node["path"])
            paths.extend(self._flatten_paths(node.get("children", [])))
        return paths


if __name__ == "__main__":
    unittest.main()
