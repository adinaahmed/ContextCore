const API_BASE = "";
const REQUEST_TIMEOUT_MS = 45000;

let authToken = localStorage.getItem("rag_token") || null;
let userEmail = localStorage.getItem("rag_email") || null;
let currentChatSessionId = "session_" + Math.random().toString(36).slice(2, 10);
let activeChatController = null;
let lastChatDateKey = null;
let selectedDocIds = [];
let allSessionsCache = [];

document.body.setAttribute("data-theme", localStorage.getItem("rag_theme") || "light");

document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("login-form").classList.toggle("hidden", tab.dataset.tab !== "login");
    document.getElementById("register-form").classList.toggle("hidden", tab.dataset.tab !== "register");
  });
});

document.querySelectorAll(".nav-item[data-view]").forEach(item => {
  item.addEventListener("click", () => {
    document.querySelectorAll(".nav-item[data-view]").forEach(i => i.classList.remove("active"));
    document.querySelectorAll(".view").forEach(v => v.classList.remove("active"));
    item.classList.add("active");
    document.getElementById("view-" + item.dataset.view).classList.add("active");
    if (item.dataset.view === "documents") loadDocuments();
    if (item.dataset.view === "history") loadSessions();
    if (item.dataset.view === "evaluation") loadEvaluationHistory();
    if (item.dataset.view === "settings") loadSettings();
    if (item.dataset.view === "ask") { populateDocScopePanel(); refreshUsageCounter(); }
  });
});

document.getElementById("sidebar-toggle").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("collapsed");
});

document.getElementById("advanced-toggle").addEventListener("click", () => {
  document.getElementById("advanced-panel").classList.toggle("hidden");
});

document.getElementById("new-chat-btn").addEventListener("click", () => {
  currentChatSessionId = "session_" + Math.random().toString(36).slice(2, 10);
  lastChatDateKey = null;
  document.getElementById("chat-window").innerHTML = `
    <div class="chat-empty" id="chat-empty-state">
      <div class="chat-empty-title">Ask anything about your documents</div>
      <div class="chat-empty-sub">Try one of these, or type your own question below.</div>
      <div class="chat-suggestions">
        <button class="suggestion-chip">What documents do you have access to?</button>
        <button class="suggestion-chip">Summarize the main topics covered</button>
        <button class="suggestion-chip">What is the most important concept here?</button>
      </div>
    </div>`;
  attachSuggestionChips();
});

function attachSuggestionChips() {
  document.querySelectorAll(".suggestion-chip").forEach(chip => {
    chip.addEventListener("click", () => {
      document.getElementById("chat-input").value = chip.textContent;
      document.getElementById("chat-form").requestSubmit();
    });
  });
}
attachSuggestionChips();

document.getElementById("login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("login-email").value;
  const password = document.getElementById("login-password").value;
  const errorEl = document.getElementById("login-error");
  errorEl.textContent = "";
  try {
    const res = await fetch(`${API_BASE}/auth/login`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Login failed");
    setSession(data.access_token, email);
    showDashboard();
  } catch (err) { errorEl.textContent = err.message; }
});

document.getElementById("register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const email = document.getElementById("register-email").value;
  const password = document.getElementById("register-password").value;
  const errorEl = document.getElementById("register-error");
  errorEl.textContent = "";
  try {
    const res = await fetch(`${API_BASE}/auth/register`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ email, password }) });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Registration failed");
    errorEl.style.color = "#3f7a4a";
    errorEl.textContent = "Account created. Switch to Log In.";
  } catch (err) { errorEl.style.color = "#a1382f"; errorEl.textContent = err.message; }
});

document.getElementById("logout-btn").addEventListener("click", () => logout());
document.getElementById("refresh-btn").addEventListener("click", loadOverview);

function setSession(token, email) {
  authToken = token; userEmail = email;
  localStorage.setItem("rag_token", token);
  localStorage.setItem("rag_email", email);
}

function logout(message) {
  authToken = null; userEmail = null;
  localStorage.removeItem("rag_token");
  localStorage.removeItem("rag_email");
  document.getElementById("dashboard-screen").classList.add("hidden");
  document.getElementById("auth-screen").classList.remove("hidden");
  document.getElementById("session-note").textContent = message || "";
}

function showDashboard() {
  document.getElementById("auth-screen").classList.add("hidden");
  document.getElementById("dashboard-screen").classList.remove("hidden");
  document.getElementById("hero-greeting").textContent = `Welcome back, ${userEmail.split("@")[0]}`;
  document.getElementById("sidebar-user").textContent = userEmail;
  loadOverview();
  populateDocScopePanel();
  refreshUsageCounter();
}

async function authedFetch(path, options = {}) {
  const controller = options.signal ? null : new AbortController();
  const timeoutId = setTimeout(() => { if (controller) controller.abort(); }, REQUEST_TIMEOUT_MS);
  try {
    const res = await fetch(`${API_BASE}${path}`, { ...options, signal: options.signal || controller.signal, headers: { "Authorization": `Bearer ${authToken}`, ...(options.headers || {}) } });
    clearTimeout(timeoutId);
    if (res.status === 401) { logout("Your session expired. Please log in again."); throw new Error("Session expired"); }
    if (!res.ok) { const err = await res.json().catch(() => ({})); throw new Error(err.detail || `${path} failed (${res.status})`); }
    if (res.status === 204) return null;
    return res.json();
  } catch (err) {
    clearTimeout(timeoutId);
    if (err.name === "AbortError") throw new Error(options.signal ? "Cancelled" : "Request timed out after 45s.");
    throw err;
  }
}

async function loadOverview() {
  const errorBox = document.getElementById("load-error");
  errorBox.classList.add("hidden"); errorBox.textContent = "";
  document.querySelectorAll(".stat-value").forEach(el => el.classList.add("skeleton"));
  try {
    const health = await fetch(`${API_BASE}/health`).then(r => r.json());
    document.getElementById("hero-status").textContent = health.status === "ok" ? "online" : "unstable";
    const [indexHealth, systemStatus] = await Promise.all([authedFetch("/index/health"), authedFetch("/system/status")]);
    setStat("stat-documents", indexHealth.documents.total, `${indexHealth.documents.current} ready`);
    setStat("stat-chunks", indexHealth.vector_store.total_chunks, `via ${indexHealth.vector_store.backend}`);
    setStat("stat-collections", indexHealth.collections.length, "");
    const isHealthy = indexHealth.orphaned_documents.count === 0 && !indexHealth.embedding_model_mixed_warning;
    setStat("stat-health", isHealthy ? "OK" : "Check", isHealthy ? "No issues found" : `${indexHealth.orphaned_documents.count} orphaned`);
    setStat("stat-provider", systemStatus.llm_provider.split(":")[0], "");
    setStat("stat-embedding", (systemStatus.embedding_provider.split(":")[1] || systemStatus.embedding_provider), "");
    setStat("stat-failed", indexHealth.documents.failed, "");
    try {
      const evalHistory = await authedFetch("/evaluation/history");
      if (evalHistory.runs && evalHistory.runs.length > 0) {
        const latest = evalHistory.runs[0];
        setStat("stat-recall", (latest.recall_at_k * 100).toFixed(0) + "%", `${latest.num_questions} questions, MRR ${latest.mrr}`);
      } else { setStat("stat-recall", "N/A", "Not evaluated"); }
    } catch { setStat("stat-recall", "N/A", "Not evaluated"); }
  } catch (err) {
    if (err.message !== "Session expired") { errorBox.textContent = err.message; errorBox.classList.remove("hidden"); }
  }
}

function setStat(id, value, sub) {
  const el = document.getElementById(id);
  el.textContent = value; el.classList.remove("skeleton");
  const subEl = document.getElementById(id + "-sub");
  if (subEl) subEl.textContent = sub;
}

function escapeHtml(str) { const div = document.createElement("div"); div.textContent = str; return div.innerHTML; }
function formatAnswer(text) {
  let escaped = escapeHtml(text);
  escaped = escaped.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  escaped = escaped.replace(/\n/g, "<br>");
  return escaped;
}
function formatClockTime(date) { return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }); }
function dayKey(date) { return date.toDateString(); }
function dayLabel(date) {
  const today = new Date();
  const yesterday = new Date(); yesterday.setDate(today.getDate() - 1);
  if (dayKey(date) === dayKey(today)) return "Today";
  if (dayKey(date) === dayKey(yesterday)) return "Yesterday";
  return date.toLocaleDateString([], { month: "long", day: "numeric", year: "numeric" });
}
function insertDateDividerIfNeeded(container, date, lastKeyRef) {
  const key = dayKey(date);
  if (lastKeyRef.value !== key) {
    lastKeyRef.value = key;
    const divider = document.createElement("div");
    divider.className = "date-divider";
    divider.innerHTML = `<span class="date-divider-pill">${dayLabel(date)}</span>`;
    container.appendChild(divider);
  }
}
function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const original = btn.textContent;
    btn.textContent = "Copied";
    btn.classList.add("copied");
    setTimeout(() => { btn.textContent = original; btn.classList.remove("copied"); }, 1500);
  });
}

document.getElementById("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("chat-input");
  const sendBtn = document.getElementById("chat-send-btn");
  const question = input.value.trim();
  if (!question) return;
  window.__lastUserQuestion = question;
  if (activeChatController) { activeChatController.abort(); return; }
  input.value = "";
  const empty = document.getElementById("chat-empty-state");
  if (empty) empty.remove();
  appendUserMessage(question);
  const typing = showTyping();
  activeChatController = new AbortController();
  sendBtn.textContent = "Stop";
  sendBtn.classList.add("btn-stop");
  const useMultiQuery = document.getElementById("opt-multi-query").checked;
  const useCompression = document.getElementById("opt-compression").checked;
  try {
    const data = await authedFetch("/query", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: activeChatController.signal,
      body: JSON.stringify({ question, top_k: 5, session_id: currentChatSessionId, use_multi_query: useMultiQuery, use_context_compression: useCompression, document_ids: selectedDocIds.length ? selectedDocIds : null }),
    });
    typing.stop();
    appendAssistantMessage(data.answer, data.citations || [], data.classification, data.confidence);
    refreshUsageCounter();
  } catch (err) {
    typing.stop();
    if (err.message === "Cancelled") appendAssistantMessage("Cancelled. Ask another question whenever you're ready.", [], null);
    else if (err.message !== "Session expired") appendAssistantMessage("Error: " + err.message, [], null);
  } finally {
    activeChatController = null;
    sendBtn.textContent = "Send";
    sendBtn.classList.remove("btn-stop");
  }
});

function appendUserMessage(text) {
  const chatWindow = document.getElementById("chat-window");
  const now = new Date();
  insertDateDividerIfNeeded(chatWindow, now, { get value() { return lastChatDateKey; }, set value(v) { lastChatDateKey = v; } });
  const row = document.createElement("div");
  row.className = "msg-row user";
  row.innerHTML = `<div class="msg"><div class="bubble">${escapeHtml(text)}</div><div class="msg-actions"><button class="msg-action-btn" data-action="copy">Copy</button><button class="msg-action-btn" data-action="edit">Edit</button></div><div class="msg-timestamp">${formatClockTime(now)}</div></div>`;
  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  row.querySelector('[data-action="copy"]').addEventListener("click", (e) => copyToClipboard(text, e.target));
  row.querySelector('[data-action="edit"]').addEventListener("click", () => { document.getElementById("chat-input").value = text; document.getElementById("chat-input").focus(); });
}

function addRegenerateButton(row, question, useMultiQuery, useCompression) {
  const actions = row.querySelector(".msg-actions");
  if (!actions) return;
  const btn = document.createElement("button");
  btn.className = "regen-btn";
  btn.textContent = "Regenerate";
  btn.addEventListener("click", async () => {
    btn.textContent = "Regenerating..."; btn.disabled = true;
    try {
      const data = await authedFetch("/query", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, top_k: 5, session_id: currentChatSessionId, use_multi_query: useMultiQuery, use_context_compression: useCompression, document_ids: selectedDocIds.length ? selectedDocIds : null }),
      });
      appendAssistantMessage(data.answer, data.citations || [], data.classification, data.confidence);
    } catch (err) {
      appendAssistantMessage("Error: " + err.message, [], null);
    } finally { btn.textContent = "Regenerate"; btn.disabled = false; }
  });
  actions.appendChild(btn);
}

function appendAssistantMessage(text, citations, classification, confidence) {
  const chatWindow = document.getElementById("chat-window");
  const now = new Date();
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  let html = `<div class="msg"><div class="bubble">${formatAnswer(text)}</div>`;
  html += `<div class="msg-meta">`;
  if (classification) html += `<span class="badge" data-cls="${classification}">${classification}</span>`;
  if (confidence) html += `<span style="font-size:11px;color:var(--ink-soft);"><span class="confidence-dot" data-level="${confidence}"></span>${confidence} confidence</span>`;
  let citId = null;
  if (citations.length > 0) {
    citId = "cit-" + Math.random().toString(36).slice(2, 8);
    html += `<button class="citations-toggle" data-target="${citId}">${citations.length} source(s)</button>`;
  }
  html += `</div>`;
  if (citId) {
    html += `<div class="citations-panel hidden" id="${citId}">`;
    citations.forEach(c => {
      const page = c.page_number ? `, page ${c.page_number}` : "";
      html += `<div class="citation-row">${escapeHtml(c.document_id || "unknown")}${page} (${escapeHtml(c.source || "")})</div>`;
    });
    html += `</div>`;
  }
  html += `<div class="msg-actions"><button class="msg-action-btn" data-action="copy">Copy</button></div>`;
  html += `<div class="msg-timestamp">${formatClockTime(now)}</div></div>`;
  row.innerHTML = html;
  chatWindow.appendChild(row);
  if (window.__lastUserQuestion) {
    addRegenerateButton(row, window.__lastUserQuestion, document.getElementById("opt-multi-query").checked, document.getElementById("opt-compression").checked);
  }
  const toggle = row.querySelector(".citations-toggle");
  if (toggle) toggle.addEventListener("click", () => document.getElementById(toggle.dataset.target).classList.toggle("hidden"));
  row.querySelector('[data-action="copy"]').addEventListener("click", (e) => copyToClipboard(text, e.target));
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function showTyping() {
  const chatWindow = document.getElementById("chat-window");
  const row = document.createElement("div");
  row.className = "msg-row assistant";
  const id = "typing-" + Date.now();
  row.id = id;
  row.innerHTML = `<div class="typing-bubble"><span class="typing-dots"><span></span><span></span><span></span></span><span class="typing-label">Thinking...</span></div>`;
  chatWindow.appendChild(row);
  chatWindow.scrollTop = chatWindow.scrollHeight;
  const label = row.querySelector(".typing-label");
  const start = Date.now();
  const interval = setInterval(() => {
    const elapsed = Math.floor((Date.now() - start) / 1000);
    if (elapsed >= 15) label.textContent = "Taking longer than usual. Click Stop to cancel.";
    else if (elapsed >= 5) label.textContent = "Retrieving and analyzing sources...";
  }, 1000);
  return { stop: () => { clearInterval(interval); const el = document.getElementById(id); if (el) el.remove(); } };
}

// --- Document scope (multi-select) ---
async function populateDocScopePanel() {
  const panel = document.getElementById("doc-scope-panel");
  if (!panel) return;
  try {
    const docs = await authedFetch("/documents");
    panel.innerHTML = docs.map(d => `
      <label class="doc-scope-option">
        <input type="checkbox" value="${escapeHtml(d.document_id)}" ${selectedDocIds.includes(d.document_id) ? "checked" : ""}>
        <span>${escapeHtml(d.document_id)}</span>
      </label>`).join("") || `<div class="empty-state">No documents yet.</div>`;
    panel.querySelectorAll("input[type=checkbox]").forEach(cb => {
      cb.addEventListener("change", () => {
        if (cb.checked) selectedDocIds.push(cb.value);
        else selectedDocIds = selectedDocIds.filter(id => id !== cb.value);
        updateDocScopeButtonLabel();
      });
    });
  } catch {}
}
function updateDocScopeButtonLabel() {
  const btn = document.getElementById("doc-scope-btn");
  if (selectedDocIds.length === 0) btn.textContent = "All documents";
  else if (selectedDocIds.length === 1) btn.textContent = selectedDocIds[0];
  else btn.textContent = `${selectedDocIds.length} documents selected`;
}
document.getElementById("doc-scope-btn").addEventListener("click", (e) => {
  e.stopPropagation();
  const panel = document.getElementById("doc-scope-panel");
  panel.classList.toggle("hidden");
  if (!panel.classList.contains("hidden")) populateDocScopePanel();
});
document.addEventListener("click", (e) => {
  const panel = document.getElementById("doc-scope-panel");
  if (panel && !panel.contains(e.target) && e.target.id !== "doc-scope-btn") panel.classList.add("hidden");
});

// --- Usage counter ---
async function refreshUsageCounter() {
  try {
    const data = await authedFetch("/query/usage");
    document.getElementById("usage-counter").textContent = `${data.questions_today} question(s) today`;
  } catch {}
}

// --- Export chat ---
document.getElementById("export-chat-btn").addEventListener("click", () => {
  const chatWindow = document.getElementById("chat-window");
  const lines = [];
  chatWindow.querySelectorAll(".msg-row").forEach(row => {
    const bubble = row.querySelector(".bubble");
    if (!bubble) return;
    const who = row.classList.contains("user") ? "You" : "Assistant";
    lines.push(`${who}: ${bubble.textContent}`);
  });
  const blob = new Blob([lines.join("\n\n")], { type: "text/plain" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url; a.download = "contextcore_chat.txt";
  a.click();
  URL.revokeObjectURL(url);
});

// --- Keyboard shortcut ---
document.addEventListener("keydown", (e) => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT" && document.getElementById("view-ask").classList.contains("active")) {
    e.preventDefault();
    document.getElementById("chat-input").focus();
  }
});

// --- Document upload (single + bulk) ---
document.getElementById("upload-file").addEventListener("change", (e) => {
  const label = document.getElementById("file-label");
  if (e.target.files.length > 1) {
    label.firstChild.textContent = `${e.target.files.length} files selected `;
    document.getElementById("upload-doc-id").required = false;
    document.getElementById("upload-doc-id").placeholder = "Not needed for bulk upload";
  } else if (e.target.files.length === 1) {
    label.firstChild.textContent = e.target.files[0].name + " ";
    const docIdField = document.getElementById("upload-doc-id");
    docIdField.required = true;
    docIdField.placeholder = "Document ID (unique)";
    if (!docIdField.value) docIdField.value = e.target.files[0].name.replace(/\.[^/.]+$/, "").replace(/\s+/g, "_").toLowerCase();
  }
});

document.getElementById("upload-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fileInput = document.getElementById("upload-file");
  const statusEl = document.getElementById("upload-status");
  statusEl.className = "upload-status"; statusEl.textContent = "";
  const existingResults = document.querySelector(".bulk-results");
  if (existingResults) existingResults.remove();

  if (!fileInput.files.length) { statusEl.className = "upload-status error"; statusEl.textContent = "Choose a file first."; return; }

  if (fileInput.files.length > 1) {
    statusEl.textContent = `Uploading ${fileInput.files.length} files...`;
    const formData = new FormData();
    for (const f of fileInput.files) formData.append("files", f);
    formData.append("strategy", document.getElementById("upload-strategy").value);
    const collection = document.getElementById("upload-collection").value;
    if (collection) formData.append("collection_id", collection);
    try {
      const res = await fetch(`${API_BASE}/ingest/bulk`, { method: "POST", headers: { "Authorization": `Bearer ${authToken}` }, body: formData });
      if (res.status === 401) { logout("Your session expired. Please log in again."); return; }
      const data = await res.json();
      statusEl.className = "upload-status success";
      statusEl.textContent = `Processed ${data.results.length} file(s).`;
      const resultsHtml = `<details class="bulk-results-details"><summary>View upload results (${data.results.length})</summary><div class="bulk-results">` + data.results.map(r => `<div class="bulk-result-row ${r.status === "error" ? "error" : "success"}">${escapeHtml(r.document_id)}: ${r.status === "error" ? escapeHtml(r.detail) : (r.chunks_created + " chunk(s), " + r.action)}</div>`).join("") + `</div></details>`;
      statusEl.insertAdjacentHTML("afterend", resultsHtml);
      document.getElementById("upload-form").reset();
      document.getElementById("file-label").firstChild.textContent = "Choose file ";
      loadDocuments();
    } catch (err) { statusEl.className = "upload-status error"; statusEl.textContent = err.message; }
    return;
  }

  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("document_id", document.getElementById("upload-doc-id").value);
  formData.append("strategy", document.getElementById("upload-strategy").value);
  const collection = document.getElementById("upload-collection").value;
  if (collection) formData.append("collection_id", collection);
  statusEl.textContent = "Uploading and processing...";
  try {
    const res = await fetch(`${API_BASE}/ingest/file`, { method: "POST", headers: { "Authorization": `Bearer ${authToken}` }, body: formData });
    if (res.status === 401) { logout("Your session expired. Please log in again."); return; }
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    statusEl.className = "upload-status success";
    statusEl.textContent = `${data.action === "unchanged" ? "Unchanged" : data.action}: ${data.chunks_created} chunk(s) processed.`;
    document.getElementById("upload-form").reset();
    document.getElementById("file-label").firstChild.textContent = "Choose file ";
    loadDocuments();
  } catch (err) { statusEl.className = "upload-status error"; statusEl.textContent = err.message; }
});

async function populateDocCollectionFilter() {
  const select = document.getElementById("doc-collection-filter");
  if (!select) return;
  try {
    const collections = await authedFetch("/collections");
    const current = select.value;
    select.innerHTML = `<option value="">All documents</option>` + collections.map(c => `<option value="${escapeHtml(c.collection_id)}">${escapeHtml(c.collection_id)} (${c.document_count})</option>`).join("");
    select.value = current;
  } catch {}
}

document.getElementById("doc-collection-filter") && document.getElementById("doc-collection-filter").addEventListener("change", (e) => {
  loadDocuments(e.target.value || null);
});

async function loadDocuments(collectionId) {
  const listEl = document.getElementById("doc-list");
  listEl.innerHTML = `<div class="empty-state">Loading documents...</div>`;
  populateDocCollectionFilter();
  try {
    const query = collectionId ? `?collection_id=${encodeURIComponent(collectionId)}` : "";
    const docs = await authedFetch(`/documents${query}`);
    if (!docs.length) { listEl.innerHTML = `<div class="empty-state">No documents yet. Upload one above.</div>`; return; }
    listEl.innerHTML = docs.map(d => `
      <div class="doc-card">
        <div class="doc-info" data-open="${escapeHtml(d.document_id)}" data-has-original="${d.has_original ? "true" : "false"}">
          <div class="doc-id">${escapeHtml(d.document_id)}${d.has_original ? "" : " (text only)"}</div>
          <div class="doc-meta">v${d.version} &middot; ${escapeHtml(d.source || "")} &middot; ${escapeHtml(d.collection_id || "no collection")} &middot; ${escapeHtml(d.chunking_strategy || "")}</div>
        </div>
        <div class="doc-right">
          <span class="doc-status" data-status="${d.processing_status}">${d.processing_status}</span>
          <button class="text-link-btn" data-inspect="${escapeHtml(d.document_id)}" title="See how this document was processed">View processing details</button>
          <button class="icon-btn" data-delete="${escapeHtml(d.document_id)}" title="Delete document">Delete</button>
        </div>
      </div>`).join("");
    listEl.querySelectorAll("[data-open]").forEach(el => {
      el.addEventListener("click", () => {
        if (el.dataset.hasOriginal !== "true") {
          alert("The original file for this document isn't available (older upload, or the file was too large to store). Use \'View processing details\' to inspect it instead.");
          return;
        }
        const url = `${window.location.origin}/documents/${encodeURIComponent(el.dataset.open)}/download?token=${encodeURIComponent(authToken)}`;
        window.open(url, "_blank");
      });
    });
    listEl.querySelectorAll("[data-inspect]").forEach(btn => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const url = `${window.location.origin}/documents/${encodeURIComponent(btn.dataset.inspect)}/view?token=${encodeURIComponent(authToken)}`;
        window.open(url, "_blank");
      });
    });
    listEl.querySelectorAll("[data-delete]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!confirm(`Delete document "${btn.dataset.delete}"? This cannot be undone.`)) return;
        try { await authedFetch(`/documents/${encodeURIComponent(btn.dataset.delete)}`, { method: "DELETE" }); loadDocuments(); }
        catch (err) { alert("Delete failed: " + err.message); }
      });
    });
  } catch (err) {
    if (err.message !== "Session expired") listEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
  }
}

// --- Chat History (with search) ---
function renderSessionList(sessions) {
  const listEl = document.getElementById("session-list-inner");
  if (!sessions.length) { listEl.innerHTML = `<div class="empty-state">No matching sessions.</div>`; return; }
  listEl.innerHTML = sessions.map(s => `
    <div class="session-card" data-session="${escapeHtml(s.session_id)}">
      <div class="session-card-text">
        <div class="session-card-question">${escapeHtml(s.last_question || "(empty session)")}</div>
        <div class="session-card-meta">${s.message_count} message(s) &middot; ${new Date(s.created_at).toLocaleDateString()}</div>
      </div>
      <button class="icon-btn" data-delete-session="${escapeHtml(s.session_id)}" title="Delete conversation">Delete</button>
    </div>`).join("");
  listEl.querySelectorAll(".session-card").forEach(card => {
    card.addEventListener("click", (e) => {
      if (e.target.closest("[data-delete-session]")) return;
      listEl.querySelectorAll(".session-card").forEach(c => c.classList.remove("active"));
      card.classList.add("active");
      loadSessionDetail(card.dataset.session);
    });
  });
  listEl.querySelectorAll("[data-delete-session]").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!confirm("Delete this conversation? This cannot be undone.")) return;
      try {
        await authedFetch(`/query/sessions/${encodeURIComponent(btn.dataset.deleteSession)}`, { method: "DELETE" });
        document.getElementById("session-detail").innerHTML = `<div class="empty-state">Select a session to view its messages.</div>`;
        loadSessions();
      } catch (err) { alert("Delete failed: " + err.message); }
    });
  });
}

document.getElementById("history-search").addEventListener("input", (e) => {
  const q = e.target.value.toLowerCase();
  const filtered = allSessionsCache.filter(s => (s.last_question || "").toLowerCase().includes(q));
  renderSessionList(filtered);
});

async function loadSessions() {
  const listEl = document.getElementById("session-list-inner");
  listEl.innerHTML = `<div class="empty-state">Loading sessions...</div>`;
  try {
    const sessions = await authedFetch("/query/sessions");
    allSessionsCache = sessions;
    renderSessionList(sessions);
  } catch (err) {
    if (err.message !== "Session expired") listEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadSessionDetail(sessionId) {
  const detailEl = document.getElementById("session-detail");
  detailEl.innerHTML = `<div class="empty-state">Loading...</div>`;
  try {
    const data = await authedFetch(`/query/history/${encodeURIComponent(sessionId)}`);

    const continueBar = document.createElement("div");
    continueBar.className = "continue-chat-bar";
    continueBar.innerHTML = `<button class="btn-secondary btn-small" id="continue-chat-btn">Continue this conversation</button>`;

    let lastKey = null;
    const lastKeyRef = { get value() { return lastKey; }, set value(v) { lastKey = v; } };
    const wrapper = document.createElement("div");
    if (data.summary) {
      const s = document.createElement("div");
      s.className = "citations-panel";
      s.style.marginBottom = "16px";
      s.innerHTML = `<strong>Summary:</strong><br>${escapeHtml(data.summary)}`;
      wrapper.appendChild(s);
    }
    data.turns.forEach(t => {
      const date = t.timestamp ? new Date(t.timestamp) : new Date();
      insertDateDividerIfNeeded(wrapper, date, lastKeyRef);
      const row1 = document.createElement("div");
      row1.className = "msg-row user";
      row1.innerHTML = `<div class="msg"><div class="bubble">${escapeHtml(t.question)}</div><div class="msg-timestamp">${formatClockTime(date)}</div></div>`;
      wrapper.appendChild(row1);
      const row2 = document.createElement("div");
      row2.className = "msg-row assistant";
      row2.style.marginBottom = "16px";
      row2.innerHTML = `<div class="msg"><div class="bubble">${formatAnswer(t.answer)}</div></div>`;
      wrapper.appendChild(row2);
    });
    detailEl.innerHTML = "";
    detailEl.appendChild(continueBar);
    detailEl.appendChild(wrapper);
    if (!data.turns.length) detailEl.innerHTML = `<div class="empty-state">No messages in this session.</div>`;

    document.getElementById("continue-chat-btn").addEventListener("click", () => {
      currentChatSessionId = sessionId;
      lastChatDateKey = null;
      const chatWindow = document.getElementById("chat-window");
      chatWindow.innerHTML = "";
      let ck = null;
      data.turns.forEach(t => {
        const date = t.timestamp ? new Date(t.timestamp) : new Date();
        insertDateDividerIfNeeded(chatWindow, date, { get value() { return ck; }, set value(v) { ck = v; } });
        appendUserMessage(t.question);
        appendAssistantMessage(t.answer, [], null, null);
      });
      lastChatDateKey = ck;
      document.querySelector('.nav-item[data-view="ask"]').click();
      setTimeout(() => document.getElementById("chat-input").focus(), 50);
    });
  } catch (err) {
    if (err.message !== "Session expired") detailEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
  }
}

// --- RAG Pipeline trace ---
document.getElementById("trace-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const input = document.getElementById("trace-input");
  const btn = document.getElementById("trace-send-btn");
  const resultEl = document.getElementById("trace-result");
  const question = input.value.trim();
  if (!question) return;
  btn.disabled = true;
  resultEl.innerHTML = `<div class="empty-state">Running question through the pipeline...</div>`;
  try {
    const data = await authedFetch("/query/trace", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ question, top_k: 5 }) });
    const stages = [];
    stages.push({ name: "Router", time: data.stages_ms && data.stages_ms.routing, detail: `Classified as: <strong>${escapeHtml(data.classification || "unknown")}</strong>` });
    if (data.classification === "direct" || data.classification === "calculation") {
      stages.push({ name: "Generation", time: data.stages_ms && data.stages_ms.generation, detail: "No retrieval needed for this question type." });
    } else {
      stages.push({ name: "Hybrid Retrieval", time: data.stages_ms && data.stages_ms.retrieval, detail: `Fused candidates: <strong>${data.fused_candidates ?? "N/A"}</strong><br>Top scores: ${(data.top_candidate_scores || []).map(s => s.toFixed(3)).join(", ") || "N/A"}` });
      stages.push({ name: "Reranking", time: data.stages_ms && data.stages_ms.reranking, detail: `Selected top <strong>${data.reranked_count ?? "N/A"}</strong> chunks.` });
      stages.push({ name: "Generation", time: data.stages_ms && data.stages_ms.generation, detail: `Context sent: <strong>${data.context_chars ?? "N/A"} characters</strong>` });
    }
    let html = `<div class="trace-flow">`;
    stages.forEach((s, i) => {
      html += `<div class="trace-node">
        <div class="trace-node-badge">${i + 1}</div>
        <div class="trace-stage">
          <div class="trace-stage-header"><span class="trace-stage-name">${escapeHtml(s.name)}</span>${s.time !== undefined ? `<span class="trace-stage-time">${s.time} ms</span>` : ""}</div>
          <div class="trace-stage-detail">${s.detail}</div>
        </div>
      </div>`;
    });
    html += `</div>`;
    html += `<div class="trace-total">Total pipeline time: ${data.total_ms ?? "N/A"} ms</div>`;
    html += `<div class="trace-stage" style="margin-top:16px;"><div class="trace-stage-header"><span class="trace-stage-name">Final Answer</span></div><div class="trace-stage-detail">${formatAnswer(data.answer || "")}</div></div>`;
    resultEl.innerHTML = html;
  } catch (err) {
    if (err.message !== "Session expired") resultEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
  } finally { btn.disabled = false; }
});


// --- Evaluation ---
document.getElementById("run-eval-btn").addEventListener("click", async () => {
  const statusEl = document.getElementById("eval-status");
  statusEl.className = "upload-status"; statusEl.textContent = "Running evaluation...";
  try {
    const data = await authedFetch("/evaluation/run?k=5", { method: "POST" });
    if (data.status === "not_evaluated") { statusEl.className = "upload-status error"; statusEl.textContent = data.message; return; }
    statusEl.className = "upload-status success";
    statusEl.textContent = `Done: Recall@${data.k_value} = ${(data.recall_at_k * 100).toFixed(0)}%, MRR = ${data.mrr}`;
    loadEvaluationHistory();
  } catch (err) { statusEl.className = "upload-status error"; statusEl.textContent = err.message; }
});

async function loadEvaluationHistory() {
  const listEl = document.getElementById("eval-history");
  listEl.innerHTML = `<div class="empty-state">Loading evaluation history...</div>`;
  try {
    const data = await authedFetch("/evaluation/history");
    if (!data.runs || !data.runs.length) { listEl.innerHTML = `<div class="empty-state">No evaluation runs yet. Click "Run Evaluation" above.</div>`; return; }
    listEl.innerHTML = data.runs.map(r => `
      <div class="doc-card">
        <div class="doc-info">
          <div class="doc-id">Recall@${r.k_value}: ${(r.recall_at_k * 100).toFixed(0)}% &middot; MRR ${r.mrr}</div>
          <div class="doc-meta">${r.num_questions} questions &middot; ${r.embedding_model || ""} &middot; ${new Date(r.run_at).toLocaleString()}</div>
        </div>
      </div>`).join("");
  } catch (err) {
    if (err.message !== "Session expired") listEl.innerHTML = `<div class="empty-state">Error: ${escapeHtml(err.message)}</div>`;
  }
}

// --- Settings ---
document.getElementById("opt-dark-mode").addEventListener("change", (e) => {
  const theme = e.target.checked ? "dark" : "light";
  document.body.setAttribute("data-theme", theme);
  localStorage.setItem("rag_theme", theme);
});

async function loadSettings() {
  document.getElementById("settings-email").textContent = userEmail || "—";
  document.getElementById("opt-dark-mode").checked = document.body.getAttribute("data-theme") === "dark";
  try {
    const systemStatus = await authedFetch("/system/status");
    document.getElementById("settings-provider").textContent = systemStatus.llm_provider;
    document.getElementById("settings-embedding").textContent = systemStatus.embedding_provider;
  } catch {}
}

async function initSession() {
  if (!authToken || !userEmail) return;
  try { await authedFetch("/system/status"); showDashboard(); } catch {}
}

initSession();

document.addEventListener("click", (e) => {
  const panel = document.getElementById("advanced-panel");
  const toggle = document.getElementById("advanced-toggle");
  if (panel && !panel.classList.contains("hidden") && !panel.contains(e.target) && e.target !== toggle) {
    panel.classList.add("hidden");
  }
});

function updateAdvancedStatusChip() {
  const chip = document.getElementById("advanced-status-chip");
  if (!chip) return;
  const active = [];
  if (document.getElementById("opt-multi-query").checked) active.push("Multi-query");
  if (document.getElementById("opt-compression").checked) active.push("Compression");
  if (active.length) {
    chip.textContent = "Active: " + active.join(", ");
    chip.classList.remove("hidden");
  } else {
    chip.classList.add("hidden");
  }
}
document.getElementById("opt-multi-query").addEventListener("change", updateAdvancedStatusChip);
document.getElementById("opt-compression").addEventListener("change", updateAdvancedStatusChip);
updateAdvancedStatusChip();
