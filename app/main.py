from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel, Field

from app.answers import UncitedAnswerError, generate_cited_answer
from app.extraction import MAX_FILE_BYTES
from app.library import Library

ROOT = Path(__file__).resolve().parent.parent
logger = logging.getLogger(__name__)


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=1200)
    top_k: int = Field(default=5, ge=1, le=8)
    use_openai: bool = False


def create_app(
    data_dir: Path | None = None,
    openai_client=None,
    enable_openai: bool = True,
    model: str | None = None,
) -> FastAPI:
    resolved_data_dir = Path(
        data_dir or os.getenv("DOCS_DATA_DIR", str(ROOT / "data"))
    ).resolve()
    library = Library(resolved_data_dir)
    if enable_openai and openai_client is None and os.getenv("OPENAI_API_KEY"):
        openai_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

    application = FastAPI(title="Document Intelligence Copilot", version="0.1.0")
    application.state.library = library
    application.state.openai_client = openai_client if enable_openai else None
    application.state.openai_model = model or os.getenv("OPENAI_MODEL", "gpt-6-luna")
    application.mount("/static", StaticFiles(directory=ROOT / "web"), name="static")

    @application.get("/")
    def home() -> FileResponse:
        return FileResponse(ROOT / "web" / "index.html")

    @application.get("/api/health")
    def health() -> dict:
        return {
            "status": "ok",
            "ai_enabled": application.state.openai_client is not None,
            "storage": "local SQLite",
        }

    @application.get("/api/documents")
    def documents() -> dict:
        return {"documents": library.list_documents()}

    @application.post("/api/documents")
    async def upload_document(file: UploadFile = File(...)) -> dict:
        filename = file.filename or "document"
        data = await file.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail="Each file must be 20 MB or smaller.")
        try:
            document, duplicate = library.add_file(filename, data)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {"document": document, "duplicate": duplicate}

    @application.delete("/api/documents/{document_id}")
    def delete_document(document_id: str) -> dict:
        if not library.delete_document(document_id):
            raise HTTPException(status_code=404, detail="Document not found.")
        return {"deleted": True}

    @application.post("/api/ask")
    def ask(request: AskRequest) -> dict:
        question = request.question.strip()
        if len(question) < 3:
            raise HTTPException(status_code=422, detail="Ask a question with at least 3 characters.")
        if request.use_openai and application.state.openai_client is None:
            raise HTTPException(
                status_code=400,
                detail="Optional AI answers are not configured. Add OPENAI_API_KEY to your local environment.",
            )
        results = library.search(question, limit=request.top_k)
        sources = [
            {
                "id": f"S{index}",
                "chunk_id": result["chunk_id"],
                "document_id": result["document_id"],
                "filename": result["filename"],
                "location": (
                    f"page {result['page_number']}"
                    if result["page_number"] is not None
                    else f"passage {result['chunk_index'] + 1}"
                ),
                "excerpt": result["text"],
                "relevance": round(-float(result["rank"]), 4),
            }
            for index, result in enumerate(results, start=1)
        ]

        if not sources:
            return {
                "answer": "I couldn't find supporting passages. Try different wording or add a document that covers this topic.",
                "mode": "local",
                "sources": [],
            }

        if request.use_openai:
            client = application.state.openai_client
            try:
                answer, cited_ids = generate_cited_answer(
                    question, sources, client, application.state.openai_model
                )
            except UncitedAnswerError as exc:
                raise HTTPException(status_code=502, detail=str(exc)) from exc
            except Exception as exc:
                logger.warning("Optional OpenAI answer request failed.")
                raise HTTPException(
                    status_code=502,
                    detail="The AI answer could not be generated. Your local library was not changed.",
                ) from exc
            cited_sources = [source for source in sources if source["id"] in cited_ids]
            return {"answer": answer, "mode": "openai", "sources": cited_sources}

        return {
            "answer": (
                f"I found {len(sources)} relevant passage(s). AI synthesis is off; "
                "review the retrieved excerpts below. Your files and search stay on this machine."
            ),
            "mode": "local",
            "sources": sources,
        }

    return application


app = create_app()
