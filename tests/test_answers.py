from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from app.answers import UncitedAnswerError, generate_cited_answer


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.sources = [{
            "id": "S1",
            "filename": "policy.md",
            "location": "passage 1",
            "excerpt": "Claims are due within 30 days.",
        }]
        self.client = Mock()

    def test_returns_answer_with_only_retrieved_citations(self):
        self.client.responses.create.return_value = SimpleNamespace(
            output_text="Claims are due within 30 days [S1]."
        )
        answer, citations = generate_cited_answer("When is it due?", self.sources, self.client, "test-model")
        self.assertEqual(answer, "Claims are due within 30 days [S1].")
        self.assertEqual(citations, {"S1"})

    def test_rejects_unknown_citation_ids(self):
        self.client.responses.create.return_value = SimpleNamespace(output_text="It's due tomorrow [S9].")
        with self.assertRaisesRegex(UncitedAnswerError, "unknown citation"):
            generate_cited_answer("When is it due?", self.sources, self.client, "test-model")

    def test_rejects_uncited_answer(self):
        self.client.responses.create.return_value = SimpleNamespace(output_text="It is due in 30 days.")
        with self.assertRaisesRegex(UncitedAnswerError, "without a source citation"):
            generate_cited_answer("When is it due?", self.sources, self.client, "test-model")


if __name__ == "__main__":
    unittest.main()
