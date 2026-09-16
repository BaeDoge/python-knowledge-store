let currentCategory = "";
let searchTimer = null;
let editingId = null;

const $ = (id) => document.getElementById(id);

// 모달은 바깥 클릭으로 닫지 않습니다. ESC / X / 취소 버튼으로만 닫습니다.
document.addEventListener("DOMContentLoaded", async () => {
  $("categoryList").addEventListener("click", (e) => {
    const button = e.target.closest(".category-btn");
    if (!button || e.target.closest(".category-delete")) return;
    e.preventDefault();
    selectCategory(button.dataset.category || "");
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("modal") && !$("modal").classList.contains("hidden")) {
      closeEditor();
    }
  });

  await loadCategories();
  await loadCurrent();

  $("searchInput").addEventListener("keydown", (e) => {
    if (e.ctrlKey && e.key.toLowerCase() === "k") {
      e.preventDefault();
      $("searchInput").focus();
    }
    if (e.key === "Escape" && $("modal") && !$("modal").classList.contains("hidden")) return;
    if (e.key === "Escape") {
      $("searchInput").value = "";
      loadCurrent();
    }
  });
});

async function loadCategories() {
  const res = await fetch("/api/categories");
  const data = await res.json();
  const nav = $("categoryList");
  nav.innerHTML = `
    <div class="category-head">
      <span class="side-label">카테고리</span>
      <button type="button" class="category-add" title="카테고리 추가" onclick="addCategory(event)">＋</button>
    </div>
    <button type="button" class="category-btn ${currentCategory === "" ? "active" : ""}" data-category="">
      <span class="cat-dot"></span>전체
    </button>`;

  data.categories.forEach(cat => {
    nav.insertAdjacentHTML("beforeend", `
      <div class="category-row">
        <button type="button" class="category-btn ${currentCategory === cat ? "active" : ""}" data-category="${escapeAttr(cat)}">
          <span class="cat-dot"></span>${escapeHtml(cat)}
        </button>
        <button type="button" class="category-delete" title="카테고리 삭제" data-category-delete="${escapeAttr(cat)}" onclick="deleteCategory(event, this.dataset.categoryDelete)">×</button>
      </div>`);
  });

  const categorySelect = $("category");
  categorySelect.innerHTML = `<option value="">미분류</option>` +
    data.categories.map(cat => `<option value="${escapeAttr(cat)}">${escapeHtml(cat)}</option>`).join("");
}

async function addCategory(event) {
  event.stopPropagation();
  const name = window.prompt("추가할 카테고리 이름을 입력하세요.");
  if (name === null) return;
  const trimmed = name.trim();
  if (!trimmed) {
    showToast("카테고리명을 입력하세요.");
    return;
  }

  const res = await fetch("/api/categories", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({name: trimmed}),
  });
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || "카테고리 추가에 실패했습니다.");
    return;
  }
  await loadCategories();
  $("category").value = trimmed;
  showToast(`'${trimmed}' 카테고리를 추가했습니다.`);
}

async function deleteCategory(event, category) {
  event.stopPropagation();
  if (!category) return;
  if (!confirm(`'${category}' 카테고리를 삭제할까요?\n해당 카테고리의 지식은 삭제되지 않고 미분류로 남습니다.`)) return;

  const res = await fetch(`/api/categories?name=${encodeURIComponent(category)}`, {method: "DELETE"});
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || "카테고리 삭제에 실패했습니다.");
    return;
  }

  if (currentCategory === category) currentCategory = "";
  await loadCategories();
  await loadCurrent();
  showToast(`'${category}' 카테고리를 삭제했습니다.`);
}

async function selectCategory(category) {
  currentCategory = category;
  await loadCategories();
  $("searchInput").value = "";
  await loadCurrent();
}

async function loadCurrent() {
  const q = $("searchInput").value.trim();
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (currentCategory) params.set("category", currentCategory);
  params.set("limit", q ? "30" : "100");
  const url = q ? `/api/search?${params.toString()}` : `/api/knowledge?${params.toString()}`;
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) {
    showToast(data.detail || "지식을 불러오지 못했습니다.");
    return;
  }
  renderCards(data.items || []);
  $("sectionLabel").textContent = q ? `"${q}" 검색 결과` : (currentCategory || "최근 지식");
  $("searchHint").textContent = q ? `${data.items.length}개의 지식을 찾았습니다.` : "몇 글자만 입력해도 바로 찾아드립니다.";
}

function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(loadCurrent, 120);
}

function renderCards(items) {
  $("countBadge").textContent = items.length;
  const container = $("cards");
  if (!items.length) {
    container.innerHTML = `<div class="empty"><div class="empty-icon">⌁</div><div>아직 지식이 없습니다.</div><div style="font-size:11px;margin-top:5px">첫 번째 지식을 기록해보세요.</div></div>`;
    return;
  }
  container.innerHTML = items.map(item => {
    const preview = (item.content || "").replace(/\s+/g, " ").trim();
    const tags = (item.tags || "").split(",").map(x => x.trim()).filter(Boolean).join("  ·  ");
    const files = item.attachments || [];
    return `<article class="card" onclick="openEditor(${item.id})">
      <div class="card-top"><span class="card-category">${escapeHtml(item.category || "미분류")}</span>${files.length ? `<span class="attachment-badge">📎 ${files.length}</span>` : ""}</div>
      <h3>${escapeHtml(item.title)}</h3>
      <p>${escapeHtml(preview || "내용 없음")}</p>
      <div class="card-bottom"><span class="tags">${escapeHtml(tags)}</span><span class="date">${formatDate(item.updated_at)}</span></div>
    </article>`;
  }).join("");
}

async function openEditor(id = null) {
  editingId = id;
  $("modal").classList.remove("hidden");
  $("knowledgeForm").reset();
  $("knowledgeId").value = "";
  $("deleteBtn").classList.toggle("hidden", !id);
  $("modalEyebrow").textContent = id ? "EDIT KNOWLEDGE" : "NEW KNOWLEDGE";
  $("modalTitle").textContent = id ? "지식 수정" : "새 지식";

  // v2 파일 기능에서 누락됐던 요소를 항상 초기화합니다.
  $("existingAttachments").innerHTML = "";
  $("attachmentInput").value = "";
  await loadCategories();

  if (id) {
    const res = await fetch(`/api/knowledge/${id}`);
    const item = await res.json();
    if (!res.ok) { showToast(item.detail || "지식을 불러오지 못했습니다."); return; }
    $("knowledgeId").value = item.id;
    $("title").value = item.title;
    $("category").value = item.category;
    $("tags").value = item.tags || "";
    $("content").value = item.content || "";
    renderAttachments(item.attachments || []);
  } else {
    $("category").value = currentCategory || "";
    renderAttachments([]);
  }
  setTimeout(() => $("title").focus(), 50);
}

function closeEditor() {
  $("modal").classList.add("hidden");
  editingId = null;
}

async function saveKnowledge(e) {
  e.preventDefault();
  const input = $("attachmentInput");
  if (!input) {
    showToast("첨부파일 입력 요소를 찾을 수 없습니다. 페이지를 새로고침하세요.");
    return;
  }

  const formData = new FormData();
  formData.append("title", $("title").value);
  formData.append("category", $("category").value);
  formData.append("tags", $("tags").value);
  formData.append("content", $("content").value);
  for (const file of input.files) formData.append("files", file);

  const id = $("knowledgeId").value;
  const res = await fetch(id ? `/api/knowledge/${id}` : "/api/knowledge", {
    method: id ? "PUT" : "POST",
    body: formData,
  });
  const data = await res.json();
  if (!res.ok) { showToast(data.detail || "저장에 실패했습니다."); return; }
  closeEditor();
  showToast(id ? "지식을 수정했습니다." : "지식을 저장했습니다.");
  await loadCurrent();
}

function renderAttachments(files) {
  const container = $("existingAttachments");
  if (!files.length) {
    container.innerHTML = `<div class="attachment-empty">첨부파일이 없습니다.</div>`;
    return;
  }
  container.innerHTML = files.map(file => {
    const isImage = (file.content_type || "").startsWith("image/");
    return `<div class="attachment-item">
      <div class="attachment-main">
        ${isImage ? `<img class="attachment-thumb" src="${escapeAttr(file.url)}" alt="">` : `<span class="file-icon">📎</span>`}
        <div><a href="${escapeAttr(file.url)}" target="_blank">${escapeHtml(file.filename)}</a><small>${formatBytes(file.file_size)}</small></div>
      </div>
      <button type="button" class="attachment-delete" onclick="deleteAttachment(${file.id}, event)">삭제</button>
    </div>`;
  }).join("");
}

async function deleteAttachment(id, event) {
  event.stopPropagation();
  if (!confirm("이 첨부파일을 삭제할까요?")) return;
  const res = await fetch(`/api/attachments/${id}`, {method: "DELETE"});
  if (!res.ok) { showToast("첨부파일 삭제에 실패했습니다."); return; }
  if (editingId) {
    const detail = await fetch(`/api/knowledge/${editingId}`).then(r => r.json());
    renderAttachments(detail.attachments || []);
  }
  showToast("첨부파일을 삭제했습니다.");
}

async function deleteKnowledge() {
  if (!editingId || !confirm("이 지식을 삭제할까요?")) return;
  const res = await fetch(`/api/knowledge/${editingId}`, {method: "DELETE"});
  if (res.ok) { closeEditor(); showToast("삭제했습니다."); await loadCurrent(); }
}

async function backup() {
  const res = await fetch("/api/backup", {method: "POST"});
  const data = await res.json();
  if (res.ok) showToast(`백업 완료: ${data.file}`);
  else showToast("백업에 실패했습니다.");
}

function formatDate(value) { return value ? value.replace("T", " ").slice(0, 16) : ""; }
function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let n = bytes, i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(i ? 1 : 0)} ${units[i]}`;
}
function showToast(text) {
  const toast = $("toast"); toast.textContent = text; toast.classList.add("show");
  setTimeout(() => toast.classList.remove("show"), 2200);
}
function escapeHtml(value) { return String(value ?? "").replace(/[&<>"']/g, ch => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch])); }
function escapeAttr(value) { return escapeHtml(value); }
