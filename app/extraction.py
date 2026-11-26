from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import PurePosixPath
import re
import zipfile

import pymupdf
from docx import Document

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PDF_PAGES = 500
MAX_DOCX_EXPANDED_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


@dataclass(frozen=True)
class ExtractedDocument:
    content_type: str
    pages: list[tuple[int | None, str]]
    page_count: int | None


def safe_filename(filename: str | None) -> str:
    name = (filename or "document").replace("\\", "/")
    name = PurePosixPath(name).name
    name = "".join(char for char in name if char.isprintable() and char not in "/\\")
    name = re.sub(r"\s+", " ", name).strip(" .")
    return (name or "document")[:160]


def extract_document(filename: str | None, data: bytes) -> ExtractedDocument:
    clean_name = safe_filename(filename)
    suffix = PurePosixPath(clean_name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Supported file types are PDF, DOCX, TXT, and Markdown.")
    if not data:
        raise ValueError("The file is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise ValueError("Each file must be 20 MB or smaller.")

    if suffix == ".pdf":
        if b"%PDF-" not in data[:1024]:
            raise ValueError("This file does not look like a PDF.")
        try:
            with pymupdf.open(stream=data, filetype="pdf") as pdf:
                if len(pdf) > MAX_PDF_PAGES:
                    raise ValueError("PDFs are limited to 500 pages.")
                pages = [(index + 1, page.get_text("text")) for index, page in enumerate(pdf)]
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This PDF could not be read. It may be damaged or password-protected.") from exc
        if not any(text.strip() for _, text in pages):
            raise ValueError("No selectable text was found. Scanned-image OCR is not included in this version.")
        return ExtractedDocument("application/pdf", pages, len(pages))

    if suffix == ".docx":
        try:
            with zipfile.ZipFile(BytesIO(data)) as archive:
                entries = archive.infolist()
                expanded_size = sum(entry.file_size for entry in entries)
                if len(entries) > 1000 or expanded_size > MAX_DOCX_EXPANDED_BYTES:
                    raise ValueError("This DOCX expands beyond the safe processing limit.")
                if archive.testzip() is not None:
                    raise ValueError("This DOCX archive is damaged.")
            document = Document(BytesIO(data))
            text = "\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())
        except ValueError:
            raise
        except Exception as exc:
            raise ValueError("This DOCX file could not be read.") from exc
        if not text.strip():
            raise ValueError("No readable text was found in this DOCX.")
        return ExtractedDocument(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            [(None, text)],
            None,
        )

    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("TXT and Markdown files must be valid UTF-8 text.") from exc
    if "\x00" in text:
        raise ValueError("This file contains binary data, not plain text.")
    if not text.strip():
        raise ValueError("No readable text was found in this file.")
    content_type = "text/markdown" if suffix == ".md" else "text/plain"
    return ExtractedDocument(content_type, [(None, text)], None)
