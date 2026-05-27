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


def test_fs_create_write_read_move_and_tree(client):
    create_response = client.post(
        "/api/fs/create-file",
        json={"path": "diary/lifecycle.md", "content": "# 初始内容"},
    )
    assert create_response.status_code == 200
    assert create_response.json()["file_path"] == "diary/lifecycle.md"

    write_response = client.post(
        "/api/fs/write",
        json={"path": "diary/lifecycle.md", "content": "# 生命周期\n更新后的内容"},
    )
    assert write_response.status_code == 200

    read_response = client.get("/api/fs/content", params={"path": "diary/lifecycle.md"})
    assert read_response.status_code == 200
    assert read_response.json()["content"] == "# 生命周期\n更新后的内容"

    move_response = client.post(
        "/api/fs/move",
        json={"old_path": "diary/lifecycle.md", "new_path": "ideas/lifecycle.md"},
    )
    assert move_response.status_code == 200
    assert move_response.json()["new_path"] == "ideas/lifecycle.md"

    moved_read_response = client.get("/api/fs/content", params={"path": "ideas/lifecycle.md"})
    assert moved_read_response.status_code == 200
    assert moved_read_response.json()["content"] == "# 生命周期\n更新后的内容"

    tree_response = client.get("/api/fs/tree")
    assert tree_response.status_code == 200
    paths = _flatten_paths(tree_response.json())
    assert "ideas/lifecycle.md" in paths
    assert "diary/lifecycle.md" not in paths


def test_fs_content_rejects_path_traversal(client, test_data_dir):
    outside_file = test_data_dir.parent / "secret.md"
    outside_file.write_text("outside data", encoding="utf-8")

    response = client.get("/api/fs/content", params={"path": "../secret.md"})

    assert response.status_code == 400
    assert "escapes data directory" in response.json()["detail"]


def _flatten_paths(nodes):
    paths = []
    for node in nodes:
        paths.append(node["path"])
        paths.extend(_flatten_paths(node.get("children", [])))
    return paths
