import unittest

from starlette.routing import Mount

from src.app.main import app


class TestStaticAssets(unittest.TestCase):
    def test_assets_static_mount_is_registered(self):
        asset_mounts = [
            route
            for route in app.routes
            if isinstance(route, Mount) and route.path == "/assets"
        ]

        self.assertEqual(len(asset_mounts), 1)


if __name__ == "__main__":
    unittest.main()


def test_root_health_response(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "DeepMemo API is running"}
