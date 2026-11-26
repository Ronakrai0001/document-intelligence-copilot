from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient

from app.main import create_app


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(data_dir=Path(self.temp.name), enable_openai=False)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.temp.cleanup()

    def test_upload_search_and_delete_flow(self):
        uploaded = self.client.post(
            "/api/documents",
            files={"file": ("travel-policy.md", b"Travel claims are due within 30 days.", "text/markdown")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        document_id = uploaded.json()["document"]["id"]

        result = self.client.post(
            "/api/ask",
            json={"question": "When are travel claims due?"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["mode"], "local")
        self.assertEqual(result.json()["sources"][0]["filename"], "travel-policy.md")
        self.assertEqual(result.json()["sources"][0]["location"], "passage 1")

        deleted = self.client.delete(f"/api/documents/{document_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/documents").json()["documents"], [])

    def test_bad_file_type_is_rejected(self):
        result = self.client.post(
            "/api/documents",
            files={"file": ("program.exe", b"not a document", "application/octet-stream")},
        )
        self.assertEqual(result.status_code, 422)

    def test_homepage_and_stylesheet_are_served(self):
        page = self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Good questions deserve", page.text)
        self.assertEqual(self.client.get("/static/app.css").status_code, 200)

    def test_ai_toggle_does_not_work_without_local_configuration(self):
        response = self.client.post(
            "/api/ask",
            json={"question": "What does the policy say?", "use_openai": True},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
