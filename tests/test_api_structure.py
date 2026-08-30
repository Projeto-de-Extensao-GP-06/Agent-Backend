import importlib
import unittest

from app.main import app


class ApiStructureTests(unittest.TestCase):
    def test_chat_router_is_in_routes_package(self):
        router_module = importlib.import_module("app.api.routes.chat")
        self.assertTrue(hasattr(router_module, "router"))

    def test_chat_route_is_registered(self):
        routes = {route.path for route in app.routes}
        self.assertIn("/api/v1/chat", routes)


if __name__ == "__main__":
    unittest.main()
