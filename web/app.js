const fileInput = document.querySelector('#file-input');
const dropzone = document.querySelector('#dropzone');
const uploadStatus = document.querySelector('#upload-status');
const documentsList = document.querySelector('#documents-list');
const answerArea = document.querySelector('#answer-area');
const emptyState = document.querySelector('#empty-state');
const askButton = document.querySelector('#ask-button');
const questionInput = document.querySelector('#question');
const aiToggle = document.querySelector('#ai-toggle');
const consent = document.querySelector('#ai-consent');

const escapeText = (value) => String(value ?? '');
const humanSize = (bytes) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`;

async function request(path, options = {}) {
  const response = await fetch(path, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || 'The request could not be completed.');
  return result;
}

function addText(parent, tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  node.textContent = escapeText(text);
  parent.append(node);
  return node;
}

async function refreshDocuments() {
  const { documents } = await request('/api/documents');
  documentsList.replaceChildren();
  document.querySelector('#document-count').textContent = documents.length;
  const heading = dropzone.querySelector('strong');
  heading.textContent = documents.length ? 'Add another document' : 'Add your first document';
  documents.forEach((item) => {
    const row = document.createElement('li'); row.className = 'document-row';
    const extension = item.filename.split('.').pop().slice(0, 4).toUpperCase();
    addText(row, 'span', 'file-mark', extension);
    const info = document.createElement('div'); info.className = 'document-info';
    addText(info, 'strong', '', item.filename);
    addText(info, 'span', '', `${humanSize(item.size_bytes)} · ${item.chunk_count} passages`);
    row.append(info);
    const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'delete-button'; remove.textContent = '×'; remove.setAttribute('aria-label', `Remove ${item.filename}`);
    remove.addEventListener('click', async () => {
      if (!window.confirm(`Remove “${item.filename}” from this local library?`)) return;
      try { await request(`/api/documents/${encodeURIComponent(item.id)}`, { method: 'DELETE' }); await refreshDocuments(); }
      catch (error) { uploadStatus.textContent = error.message; uploadStatus.className = 'status error'; }
    });
    row.append(remove); documentsList.append(row);
  });
}

async function upload(file) {
  if (!file) return;
  uploadStatus.textContent = `Indexing ${file.name}…`; uploadStatus.className = 'status';
  const form = new FormData(); form.append('file', file);
  try {
    const result = await request('/api/documents', { method: 'POST', body: form });
    uploadStatus.textContent = result.duplicate ? 'This document is already in your library.' : `Added ${result.document.filename}.`;
    await refreshDocuments();
  } catch (error) { uploadStatus.textContent = error.message; uploadStatus.className = 'status error'; }
  fileInput.value = '';
}

function showAnswer(result) {
  answerArea.replaceChildren();
  const answer = document.createElement('article'); answer.className = 'answer-card';
  addText(answer, 'p', 'answer-label', result.mode === 'openai' ? 'AI DRAFT · CHECK THE SOURCES' : 'LOCAL RETRIEVAL');
  addText(answer, 'p', 'answer-text', result.answer);
  answerArea.append(answer);
  if (result.sources.length) {
    addText(answerArea, 'h2', 'sources-heading', `Retrieved sources (${result.sources.length})`);
    result.sources.forEach((source) => {
      const card = document.createElement('article'); card.className = 'source-card';
      addText(card, 'div', 'source-meta', `${source.id} · ${source.filename} · ${source.location}`);
      addText(card, 'div', 'source-text', source.excerpt);
      answerArea.append(card);
    });
  }
  emptyState.hidden = true;
}

dropzone.addEventListener('click', () => fileInput.click());
document.querySelector('#add-document').addEventListener('click', () => fileInput.click());
document.querySelector('#empty-upload').addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', () => upload(fileInput.files[0]));
dropzone.addEventListener('dragover', (event) => { event.preventDefault(); dropzone.classList.add('dragging'); });
dropzone.addEventListener('dragleave', () => dropzone.classList.remove('dragging'));
dropzone.addEventListener('drop', (event) => { event.preventDefault(); dropzone.classList.remove('dragging'); upload(event.dataTransfer.files[0]); });
aiToggle.addEventListener('change', () => { consent.hidden = !aiToggle.checked; });
askButton.addEventListener('click', async () => {
  const question = questionInput.value.trim();
  if (question.length < 3) { questionInput.focus(); return; }
  askButton.disabled = true; askButton.firstElementChild.textContent = 'Searching…';
  answerArea.replaceChildren();
  try {
    const result = await request('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question, use_openai: aiToggle.checked }) });
    showAnswer(result);
  } catch (error) {
    const notice = document.createElement('p'); notice.className = 'notice'; notice.textContent = error.message; answerArea.replaceChildren(notice);
  } finally { askButton.disabled = false; askButton.firstElementChild.textContent = 'Ask'; }
});
questionInput.addEventListener('keydown', (event) => { if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') askButton.click(); });
document.querySelector('#load-demo').addEventListener('click', async () => {
  const button = document.querySelector('#load-demo'); button.disabled = true; button.textContent = 'Loading sample…';
  try {
    const result = await request('/api/demo', { method: 'POST' });
    uploadStatus.textContent = result.duplicate ? 'Demo handbook is already in your library.' : 'Fictional demo handbook added.';
    await refreshDocuments();
    questionInput.value = 'How soon should I report a lost laptop?';
  } catch (error) { uploadStatus.textContent = error.message; uploadStatus.className = 'status error'; }
  finally { button.disabled = false; button.textContent = 'Or load the fictional demo handbook'; }
});

refreshDocuments().catch((error) => { uploadStatus.textContent = error.message; uploadStatus.className = 'status error'; });
