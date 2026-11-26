from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import httpx

from app.main import create_app


class ApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = create_app(data_dir=Path(self.temp.name), enable_openai=False)
        self.client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=self.app), base_url="http://test"
        )

    async def asyncTearDown(self):
        await self.client.aclose()
        self.temp.cleanup()

    async def test_upload_search_and_delete_flow(self):
        uploaded = await self.client.post(
            "/api/documents",
            files={"file": ("travel-policy.md", b"Travel claims are due within 30 days.", "text/markdown")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)
        document_id = uploaded.json()["document"]["id"]

        result = await self.client.post(
            "/api/ask",
            json={"question": "When are travel claims due?"},
        )
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()["mode"], "local")
        self.assertEqual(result.json()["sources"][0]["filename"], "travel-policy.md")
        self.assertEqual(result.json()["sources"][0]["location"], "passage 1")

        deleted = await self.client.delete(f"/api/documents/{document_id}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual((await self.client.get("/api/documents")).json()["documents"], [])

    async def test_bad_file_type_is_rejected(self):
        result = await self.client.post(
            "/api/documents",
            files={"file": ("program.exe", b"not a document", "application/octet-stream")},
        )
        self.assertEqual(result.status_code, 422)

    async def test_homepage_and_stylesheet_are_served(self):
        page = await self.client.get("/")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Good questions deserve", page.text)
        self.assertIn("load-demo", page.text)
        self.assertEqual((await self.client.get("/static/app.css")).status_code, 200)

    async def test_demo_load_is_idempotent_and_searchable(self):
        first = await self.client.post("/api/demo")
        self.assertEqual(first.status_code, 200, first.text)
        self.assertFalse(first.json()["duplicate"])
        self.assertEqual(first.json()["document"]["filename"], "sample-handbook.md")

        second = await self.client.post("/api/demo")
        self.assertTrue(second.json()["duplicate"])

        answer = await self.client.post(
            "/api/ask", json={"question": "How soon should I report a lost laptop?"}
        )
        self.assertEqual(answer.status_code, 200, answer.text)
        self.assertIn("one hour", answer.json()["sources"][0]["excerpt"])

    async def test_ai_toggle_does_not_work_without_local_configuration(self):
        response = await self.client.post(
            "/api/ask",
            json={"question": "What does the policy say?", "use_openai": True},
        )
        self.assertEqual(response.status_code, 400)


if __name__ == "__main__":
    unittest.main()
