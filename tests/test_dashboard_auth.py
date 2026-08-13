import unittest

from fastapi.testclient import TestClient

from app.main import app


class DashboardAuthTest(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)

    def test_dashboard_requires_authentication(self):
        response = self.client.get("/dashboard", allow_redirects=False)

        self.assertEqual(response.status_code, 401)
        self.assertIn("Unauthorized", response.text)
        self.assertIn("Please sign in to continue", response.text)


if __name__ == "__main__":
    unittest.main()
