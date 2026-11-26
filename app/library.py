from __future__ import annotations

from datetime import datetime, timezone
from contextlib import closing
import hashlib
from pathlib import Path
import re
import sqlite3
import uuid

from app.extraction import ExtractedDocument, extract_document, safe_filename

CHUNK_SIZE = 950
CHUNK_OVERLAP = 120


def chunk_pages(pages: list[tuple[int | None, str]]) -> list[dict[str, int | None | str]]:
    chunks: list[dict[str, int | None | str]] = []
    for page_number, page_text in pages:
        text = re.sub(r"\s+", " ", page_text).strip()
        start = 0
        while start < len(text):
            end = min(start + CHUNK_SIZE, len(text))
            if end < len(text):
                boundary = text.rfind(" ", start + int(CHUNK_SIZE * 0.65), end)
                if boundary > start:
                    end = boundary
            passage = text[start:end].strip()
            if passage:
                chunks.append({
                    "chunk_index": len(chunks),
                    "page_number": page_number,
                    "text": passage,
                })
            if end >= len(text):
                break
            start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


class Library:
    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.database = self.data_dir / "index.sqlite3"
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def initialize(self) -> None:
        with closing(self.connect()) as connection, connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS documents (
                    id TEXT PRIMARY KEY,
                    filename TEXT NOT NULL,
                    content_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    page_count INTEGER,
                    sha256 TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS chunks (
                    id TEXT PRIMARY KEY,
                    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
                    chunk_index INTEGER NOT NULL,
                    page_number INTEGER,
                    text TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS chunks_document_id ON chunks(document_id);
                CREATE VIRTUAL TABLE IF NOT EXISTS chunk_search
                USING fts5(chunk_id UNINDEXED, text, tokenize='unicode61 remove_diacritics 2');
                """
            )

    def add_file(self, filename: str | None, data: bytes) -> tuple[dict, bool]:
        extracted = extract_document(filename, data)
        return self.add_extracted(safe_filename(filename), data, extracted)

    def add_extracted(
        self, filename: str, data: bytes, extracted: ExtractedDocument
    ) -> tuple[dict, bool]:
        digest = hashlib.sha256(data).hexdigest()
        chunks = chunk_pages(extracted.pages)
        if not chunks:
            raise ValueError("No searchable text was found in this file.")

        with closing(self.connect()) as connection, connection:
            existing = connection.execute(
                "SELECT id FROM documents WHERE sha256 = ?", (digest,)
            ).fetchone()
            if existing:
                document = self.get_document(existing["id"], connection)
                return document, True

            document_id = uuid.uuid4().hex
            created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
            connection.execute(
                """INSERT INTO documents
                   (id, filename, content_type, size_bytes, page_count, sha256, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    document_id,
                    filename,
                    extracted.content_type,
                    len(data),
                    extracted.page_count,
                    digest,
                    created_at,
                ),
            )
            for chunk in chunks:
                chunk_id = uuid.uuid4().hex
                connection.execute(
                    """INSERT INTO chunks (id, document_id, chunk_index, page_number, text)
                       VALUES (?, ?, ?, ?, ?)""",
                    (
                        chunk_id,
                        document_id,
                        chunk["chunk_index"],
                        chunk["page_number"],
                        chunk["text"],
                    ),
                )
                connection.execute(
                    "INSERT INTO chunk_search (chunk_id, text) VALUES (?, ?)",
                    (chunk_id, chunk["text"]),
                )
            document = self.get_document(document_id, connection)
            return document, False

    def get_document(self, document_id: str, connection: sqlite3.Connection | None = None) -> dict:
        owns_connection = connection is None
        connection = connection or self.connect()
        try:
            row = connection.execute(
                """SELECT d.id, d.filename, d.content_type, d.size_bytes, d.page_count,
                          d.created_at, COUNT(c.id) AS chunk_count
                   FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                   WHERE d.id = ? GROUP BY d.id""",
                (document_id,),
            ).fetchone()
            if row is None:
                raise KeyError(document_id)
            return dict(row)
        finally:
            if owns_connection:
                connection.close()

    def list_documents(self) -> list[dict]:
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(
                """SELECT d.id, d.filename, d.content_type, d.size_bytes, d.page_count,
                          d.created_at, COUNT(c.id) AS chunk_count
                   FROM documents d LEFT JOIN chunks c ON c.document_id = d.id
                   GROUP BY d.id ORDER BY d.created_at DESC"""
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_document(self, document_id: str) -> bool:
        with closing(self.connect()) as connection, connection:
            exists = connection.execute(
                "SELECT 1 FROM documents WHERE id = ?", (document_id,)
            ).fetchone()
            if exists is None:
                return False
            connection.execute(
                """DELETE FROM chunk_search
                   WHERE chunk_id IN (SELECT id FROM chunks WHERE document_id = ?)""",
                (document_id,),
            )
            connection.execute("DELETE FROM documents WHERE id = ?", (document_id,))
            return True

    def search(self, question: str, limit: int = 5) -> list[dict]:
        terms = []
        for term in re.findall(r"[\w]+", question, flags=re.UNICODE):
            if len(term) > 1 and term.casefold() not in terms:
                terms.append(term.casefold())
            if len(terms) == 18:
                break
        if not terms:
            return []
        match = " OR ".join(f'"{term}"' for term in terms)
        with closing(self.connect()) as connection, connection:
            rows = connection.execute(
                """SELECT c.id AS chunk_id, c.document_id, d.filename, c.chunk_index,
                          c.page_number, c.text, bm25(chunk_search) AS rank
                   FROM chunk_search
                   JOIN chunks c ON c.id = chunk_search.chunk_id
                   JOIN documents d ON d.id = c.document_id
                   WHERE chunk_search MATCH ?
                   ORDER BY rank
                   LIMIT ?""",
                (match, limit),
            ).fetchall()
        return [dict(row) for row in rows]
