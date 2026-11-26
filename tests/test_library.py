from __future__ import annotations

from io import BytesIO
from pathlib import Path
import tempfile
import unittest

from docx import Document
import pymupdf

from app.extraction import extract_document, safe_filename
from app.library import Library, chunk_pages


class ExtractionTests(unittest.TestCase):
    def test_safe_filename_discards_directory_components(self):
        self.assertEqual(safe_filename("../../policy.txt"), "policy.txt")
        self.assertEqual(safe_filename("C:\\private\\policy.txt"), "policy.txt")

    def test_text_and_markdown_are_read_as_utf8(self):
        result = extract_document("guide.md", b"Keep the original source.")
        self.assertEqual(result.content_type, "text/markdown")
        self.assertIn("original source", result.pages[0][1])

    def test_docx_paragraphs_are_extracted(self):
        document = Document()
        document.add_paragraph("Approved expenses must include a receipt.")
        stream = BytesIO()
        document.save(stream)
        result = extract_document("policy.docx", stream.getvalue())
        self.assertIn("include a receipt", result.pages[0][1])

    def test_pdf_page_numbers_are_preserved(self):
        document = pymupdf.open()
        page = document.new_page()
        page.insert_text((72, 72), "The annual leave allowance is twelve days.")
        data = document.tobytes()
        document.close()
        result = extract_document("policy.pdf", data)
        self.assertEqual(result.pages[0][0], 1)
        self.assertEqual(result.page_count, 1)

    def test_rejects_unapproved_types_and_binary_text(self):
        with self.assertRaisesRegex(ValueError, "Supported file types"):
            extract_document("script.exe", b"data")
        with self.assertRaisesRegex(ValueError, "binary data"):
            extract_document("notes.txt", b"\x00")


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.library = Library(Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def test_search_returns_verifiable_chunks_and_delete_removes_them(self):
        data = (
            "Reimbursement requests must be submitted within thirty days. "
            "Attach an itemized receipt and manager approval."
        ).encode()
        document, duplicate = self.library.add_file("expenses.txt", data)
        self.assertFalse(duplicate)

        results = self.library.search("When are reimbursement requests due?", limit=3)
        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["document_id"], document["id"])
        self.assertIn("thirty days", results[0]["text"])
        self.assertIsNone(results[0]["page_number"])

        self.assertTrue(self.library.delete_document(document["id"]))
        self.assertEqual(self.library.search("reimbursement requests", limit=3), [])
        self.assertFalse(self.library.delete_document(document["id"]))

    def test_duplicate_upload_does_not_duplicate_index(self):
        data = b"Travel expenses need manager approval."
        first, is_duplicate = self.library.add_file("travel.txt", data)
        second, is_duplicate_again = self.library.add_file("renamed.txt", data)
        self.assertFalse(is_duplicate)
        self.assertTrue(is_duplicate_again)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(self.library.list_documents()), 1)

    def test_chunking_keeps_each_pdf_page_as_its_own_citation(self):
        text = "policyword " * 220
        chunks = chunk_pages([(1, text), (2, text)])
        self.assertGreater(len(chunks), 2)
        self.assertEqual({chunk["page_number"] for chunk in chunks}, {1, 2})
        self.assertLessEqual(max(len(chunk["text"]) for chunk in chunks), 950)


if __name__ == "__main__":
    unittest.main()
