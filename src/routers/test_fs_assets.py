import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

import src.routers.fs as fs_router_module


class TestFsAssetUpload(unittest.TestCase):
    def test_upload_asset_returns_vditor_response_and_writes_file(self):
        with TemporaryDirectory() as tmp_dir:
            original_data_dir = fs_router_module.DATA_DIR
            fs_router_module.DATA_DIR = Path(tmp_dir)
            try:
                app = FastAPI()
                app.include_router(fs_router_module.router)
                client = TestClient(app)

                response = client.post(
                    "/api/fs/upload-asset",
                    data={"source_path": "diary/0526.md"},
                    files={"file[]": ("screenshot.png", b"png-bytes", "image/png")},
                )
            finally:
                fs_router_module.DATA_DIR = original_data_dir

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["code"], 0)
            self.assertEqual(body["data"]["errFiles"], [])
            markdown_path = body["data"]["succMap"]["screenshot.png"]
            self.assertTrue(markdown_path.startswith("../assets/diary/2026-05-26/"))

            stored_files = list((Path(tmp_dir) / "assets/diary/2026-05-26").glob("*.png"))
            self.assertEqual(len(stored_files), 1)
            self.assertEqual(stored_files[0].read_bytes(), b"png-bytes")

    def test_upload_asset_supports_ideas_markdown_sources(self):
        with TemporaryDirectory() as tmp_dir:
            original_data_dir = fs_router_module.DATA_DIR
            fs_router_module.DATA_DIR = Path(tmp_dir)
            try:
                app = FastAPI()
                app.include_router(fs_router_module.router)
                client = TestClient(app)

                response = client.post(
                    "/api/fs/upload-asset",
                    data={"source_path": "ideas/DeepMemo.md"},
                    files={"file[]": ("architecture.png", b"png-bytes", "image/png")},
                )
            finally:
                fs_router_module.DATA_DIR = original_data_dir

            self.assertEqual(response.status_code, 200)
            body = response.json()
            self.assertEqual(body["data"]["errFiles"], [])
            self.assertTrue(
                body["data"]["succMap"]["architecture.png"].startswith("../assets/ideas/DeepMemo/"),
            )

            stored_files = list((Path(tmp_dir) / "assets/ideas/DeepMemo").glob("*.png"))
            self.assertEqual(len(stored_files), 1)
            self.assertEqual(stored_files[0].read_bytes(), b"png-bytes")


if __name__ == "__main__":
    unittest.main()
