# Document Intelligence Copilot

**Ask questions across your working documents and inspect the passages behind every result.**

This repository turns the original project brief into a usable, local-first prototype. Add PDFs, Word documents, Markdown, or plain text; search the extracted passages; and, optionally, ask an OpenAI model to write a concise answer that cites the retrieved sources.

> **Current scope:** a local single-user prototype for selectable-text documents. It is not a hosted service or a production document-management system. Search is lexical (SQLite full-text search), scanned-PDF OCR and embeddings are not implemented, and the app has no sign-in or multi-user isolation.

## What it does

- Accepts `.pdf`, `.docx`, `.txt`, and `.md` files up to 20 MB each.
- Extracts text locally and creates overlapping passages. PDF passages retain 1-based page numbers; other formats cite a passage number.
- Ranks passages with SQLite FTS5's BM25 ranking and shows the source excerpt next to each result.
- Can optionally draft a grounded answer using the OpenAI Responses API. The switch is off by default; the model receives the question and retrieved excerpts, not the original file. Its cited source IDs are checked against the retrieved set.
- Saves the search index in a local SQLite database. Original uploads are processed in memory and are not retained.
- Lets you remove documents, which deletes their passage index too.

## Run locally

Python 3.11 or newer is recommended. In PowerShell:

```powershell
cd path\to\document-intelligence-copilot
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. Keep the host bound to `127.0.0.1` for this prototype. The default index directory is `./data`; set `DOCS_DATA_DIR` to choose another local path.

### Optional AI drafting

The app works without an API key. To enable AI drafting, set `OPENAI_API_KEY` in your shell before starting the server and, optionally, set `OPENAI_MODEL` to a model available to your account:

```powershell
$env:OPENAI_API_KEY = "your-key"
$env:OPENAI_MODEL = "gpt-6-luna"
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

You must also turn on **Use AI to draft an answer** for each question. The interface explains the data transfer beside the switch. Only the question and retrieved excerpts are sent for that request. OpenAI API usage may incur charges; check your account's current pricing and model availability. The model can still make mistakes, so inspect the passages before relying on a result.

## How a question flows

1. **Upload and validate:** the server allow-lists extensions, checks file size and content, applies PDF page and DOCX archive limits, and rejects empty or unreadable documents.
2. **Extract:** PyMuPDF reads selectable PDF text page by page; python-docx reads DOCX paragraphs; UTF-8 decodes text and Markdown. Scanned PDFs need OCR and currently return a clear error.
3. **Chunk and index:** text is normalized into roughly 950-character passages with 120-character overlap, then indexed in local SQLite FTS5. PDF page boundaries remain separate.
4. **Retrieve:** question terms are matched against the local index and ranked with BM25. Results include the filename, page or passage location, and exact stored excerpt.
5. **Answer (optional):** with the per-question switch enabled and a configured API key, retrieved passages are sent to the OpenAI Responses API. The app rejects unknown source IDs and answers without a citation, then returns only the cited source cards.

The citation check catches common source-ID mistakes; it cannot prove that a sentence is entailed by a passage. Local retrieval results are evidence to inspect, not a generated answer.

## Privacy and security boundaries

- The app binds to localhost when launched using the command above. It has no authentication, CSRF protection, or multi-user boundary; do not expose it to a network as-is.
- Uploads are not saved as original files. Extracted text is stored in `data/index.sqlite3` and persists until you delete the indexed document or remove that local data directory.
- `.env`, the local `data/` directory, and Python caches are ignored by Git. Never commit API keys or real private documents.
- File names are sanitized and displayed as text. The browser builds document names and excerpts with `textContent` to avoid interpreting uploaded content as HTML.
- Archive and size limits reduce resource abuse but are not a substitute for a hardened upload service. The app is intended for documents you trust on your own machine.
- AI mode sends the question and matched passages to OpenAI. Keep the switch off for local-only use.

## Check the project

Run the unit and API tests without making any external AI calls:

```powershell
python -m unittest discover -v
```

Manual retrieval smoke questions and the bundled synthetic sample are in [`evals/README.md`](evals/README.md) and [`samples/sample-handbook.md`](samples/sample-handbook.md). The sample is fictional; use it to test the flow without uploading private material.

Health endpoint: `GET /api/health`.

| Route | Purpose |
| --- | --- |
| `GET /api/documents` | List indexed file metadata |
| `POST /api/documents` | Upload and index one file (`multipart/form-data`, field `file`) |
| `DELETE /api/documents/{id}` | Remove a document and its indexed passages |
| `POST /api/ask` | Retrieve sources and optionally draft an answer |

Example request:

```json
{"question":"How many days do I have to submit a travel claim?","top_k":5,"use_openai":false}
```

## Repository guidance and references

The repository includes the [Ponytail coding guidance](https://github.com/DietrichGebert/ponytail/tree/v5.3.3), pinned at v5.3.3 under `.agents/skills/ponytail/`. Its MIT license and upstream provenance are included. This is guidance only, not an application dependency or a license for this project.

Implementation references:

- [SQLite FTS5](https://www.sqlite.org/fts5.html) documents the local full-text index and BM25 ranking.
- [FastAPI file uploads](https://fastapi.tiangolo.com/tutorial/request-files/) documents its upload handling.
- [OpenAI API overview](https://platform.openai.com/overview) describes the current API approach used for optional model requests.
- [OWASP File Upload Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/File_Upload_Cheat_Sheet.html) informs the upload validation and size-limit choices.

## License

No application license has been selected. The copied Ponytail guidance has its own MIT license in `.agents/skills/ponytail/LICENSE`; that license applies to the copied guidance, not automatically to the application.
