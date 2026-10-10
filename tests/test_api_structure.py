import importlib
import unittest

from app.src.main import app


class ApiStructureTests(unittest.TestCase):
    def test_chat_router_is_in_routes_package(self):
        router_module = importlib.import_module("app.src.api.routes.chat")
        self.assertTrue(hasattr(router_module, "router"))

    def test_chat_route_is_registered(self):
        routes = set(app.openapi().get("paths", {}).keys())
        self.assertIn("/api/v1/chat", routes)


if __name__ == "__main__":
    unittest.main()
