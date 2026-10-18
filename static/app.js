/* CapSync frontend — без фреймворков, обычный DOM + поллинг /api/state. */

const ICON_NAMES = [
  "play", "stop", "plus", "settings", "folder", "trash", "warning", "save",
  "check", "chevron-down", "audio", "paperclip", "close",
  "check-circle", "spinner",
];
const ICONS = {};

async function loadIcons() {
  await Promise.all(ICON_NAMES.map(async (name) => {
    const res = await fetch(`/static/icons/${name}.svg`);
    ICONS[name] = await res.text();
  }));
  applyIcons(document);
}

function applyIcons(root) {
  root.querySelectorAll("[data-icon]").forEach((el) => {
    const name = el.getAttribute("data-icon");
    if (ICONS[name] && !el.dataset.filled) {
      el.innerHTML = ICONS[name];
      el.dataset.filled = "1";
    }
  });
}

function iconSpan(name, cls) {
  return `<span class="icon ${cls || ""}" data-icon="${name}">${ICONS[name] || ""}</span>`;
}

function flagImg(cc) {
  if (!cc) return `<span class="csel-flag csel-flag-blank"></span>`;
  return `<img class="csel-flag" src="/static/flags/${cc}.svg" alt="">`;
}

function escapeHtml(s) {
  return (s || "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* ---------- кастомный дропдаун (csel) — вместо системных select/datalist ---------- */

const cselRegistry = {}; // id -> {options:[{value,label,flag}], value, open, search, onChange, searchable}

function cselMount(id, opts) {
  cselRegistry[id] = { open: false, search: "", ...opts };
  return `<div class="csel" id="csel-${id}"></div>`;
}

function cselRender(id) {
  const st = cselRegistry[id];
  const el = document.getElementById(`csel-${id}`);
  if (!st || !el) return;
  const current = st.options.find((o) => o.value === st.value);
  el.classList.toggle("open", st.open);
  let panel = "";
  if (st.open) {
    const filtered = st.searchable && st.search
      ? st.options.filter((o) => o.label.toLowerCase().includes(st.search.toLowerCase()))
      : st.options;
    panel = `
      <div class="csel-panel">
        ${st.searchable ? `<input class="csel-search" placeholder="Поиск…" value="${escapeHtml(st.search)}">` : ""}
        <div class="csel-list">
          ${filtered.length ? filtered.map((o) => `
            <div class="csel-option ${o.value === st.value ? "selected" : ""}" data-value="${escapeHtml(o.value)}">
              ${o.flag !== undefined ? flagImg(o.flag) : ""}<span>${escapeHtml(o.label)}</span>
            </div>`).join("") : `<div class="csel-empty">Ничего не найдено</div>`}
        </div>
      </div>`;
  }
  el.innerHTML = `
    <button type="button" class="csel-trigger">
      ${current && current.flag !== undefined ? flagImg(current.flag) : ""}
      <span class="csel-trigger-label">${escapeHtml(current ? current.label : "—")}</span>
      ${iconSpan("chevron-down")}
    </button>
    ${panel}`;
  applyIcons(el);

  el.querySelector(".csel-trigger").onclick = (e) => {
    e.stopPropagation();
    const willOpen = !st.open;
    Object.values(cselRegistry).forEach((s) => { s.open = false; });
    st.open = willOpen;
    st.search = "";
    Object.keys(cselRegistry).forEach((k) => cselRender(k));
    if (willOpen) {
      const search = el.querySelector(".csel-search");
      if (search) search.focus();
    }
  };
  el.querySelectorAll(".csel-option").forEach((opt) => {
    opt.onclick = (e) => {
      e.stopPropagation();
      st.value = opt.dataset.value;
      st.open = false;
      cselRender(id);
      st.onChange(st.value);
    };
  });
  const search = el.querySelector(".csel-search");
  if (search) {
    search.oninput = () => { st.search = search.value; cselRender(id); search.focus(); };
    search.onclick = (e) => e.stopPropagation();
  }
}

document.addEventListener("click", () => {
  let changed = false;
  Object.values(cselRegistry).forEach((s) => { if (s.open) { s.open = false; changed = true; } });
  if (changed) Object.keys(cselRegistry).forEach((k) => cselRender(k));
});

/* ---------- глобальное состояние ---------- */

const state = {
  mode: "draft",      // draft | running | finished
  langs: [],           // [{value, label, flag}]
  settings: null,
  draftRows: [],        // [{id, text, audioFile, projectName, language, languageTouched}]
  backendState: null,   // последний /api/state
};

let rowSeq = 0;
function newDraftRow() {
  return { id: ++rowSeq, text: "", audioFile: null, projectName: "", language: "auto", languageTouched: false };
}

/* ---------- API ---------- */

const api = {
  get: (url) => fetch(url).then((r) => r.json()),
  post: (url, body) => fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}),
  }).then((r) => r.json()),
  del: (url) => fetch(url, { method: "DELETE" }).then((r) => r.json()),
  postForm: (url, formData) => fetch(url, { method: "POST", body: formData }).then((r) => r.json()),
};

/* ---------- статус задачи ---------- */

function statusIcon(status) {
  if (status === "done") return iconSpan("check-circle");
  if (status === "error") return iconSpan("warning");
  if (status === "running") return iconSpan("spinner", "spin");
  if (status === "cancelled") return iconSpan("close");
  return "";
}
function statusLineClass(status) {
  if (status === "done") return "ok";
  if (status === "error") return "err";
  if (status === "running") return "running";
  return "";
}

/* ---------- рендер очереди ---------- */

function autoGrow(el) {
  el.style.height = "auto";
  el.style.height = el.scrollHeight + "px";
}

function renderQueue() {
  const el = document.getElementById("queue");
  if (state.mode === "draft") {
    if (state.draftRows.length === 0) {
      el.innerHTML = `<div class="queue-empty">Добавь первую задачу — текст озвучки + аудиофайл.</div>`;
      return;
    }
    el.innerHTML = state.draftRows.map((row, i) => renderDraftRow(row, i)).join("");
    applyIcons(el);
    state.draftRows.forEach((row) => cselRender(`lang-${row.id}`));
    wireDraftRowEvents();
    el.querySelectorAll(".task-text").forEach(autoGrow);
  } else {
    const tasks = (state.backendState && state.backendState.tasks) || [];
    el.innerHTML = tasks.map((t, i) => renderBackendTask(t, i)).join("");
    applyIcons(el);
    wireBackendTaskEvents();
    el.querySelectorAll(".task-text").forEach(autoGrow);
  }
}

function renderDraftRow(row, i) {
  const audioLabel = row.audioFile ? row.audioFile.name : "Прикрепить файл";
  cselRegistry[`lang-${row.id}`] = cselRegistry[`lang-${row.id}`] || {
    open: false, search: "", options: state.langs, value: row.language, searchable: true,
    onChange: (v) => { row.language = v; row.languageTouched = true; },
  };
  cselRegistry[`lang-${row.id}`].options = state.langs;
  cselRegistry[`lang-${row.id}`].value = row.language;

  return `
  <div class="task" data-row-id="${row.id}">
    <div class="task-top">
      <div class="task-index">${i + 1}</div>
      <textarea class="task-text" placeholder="Вставьте текст озвучки…" data-field="text">${escapeHtml(row.text)}</textarea>
      <button class="task-remove" data-action="remove-row" title="Удалить">${iconSpan("trash")}</button>
    </div>
    <div class="task-row2">
      <label class="audio-btn ${row.audioFile ? "has-file" : ""}" data-action="audio-drop">
        ${iconSpan("paperclip")}<span>${escapeHtml(audioLabel)}</span>
        <input type="file" accept="audio/*,video/*" data-field="audio">
      </label>
      ${cselMount(`lang-${row.id}`, cselRegistry[`lang-${row.id}`])}
      <input class="name-input" placeholder="Название проекта (необязательно)" value="${escapeHtml(row.projectName)}" data-field="name">
    </div>
  </div>`;
}

function renderBackendTask(t, i) {
  // пошаговый прогресс ("распознаётся язык…", "выравниваются слова…") живёт только в общем
  // прогресс-баре снизу — в самой карточке задачи только статус-иконка в углу и, если
  // ошибка, кнопка лога (это единственное, что требует действия именно на уровне задачи).
  const errorBlock = t.status === "error" ? `
    <div class="task-error-actions">
      <button class="btn-ghost-sm" data-action="save-log" data-log="${encodeURIComponent((state.backendState.last_error||{}).log_path||"")}">
        ${iconSpan("save")} Сохранить лог
      </button>
    </div>` : "";
  return `
  <div class="task status-${t.status}">
    <div class="task-top">
      <div class="task-index">${i + 1}</div>
      <textarea class="task-text" readonly>${escapeHtml(t.text)}</textarea>
      <div class="task-status-badge ${statusLineClass(t.status)}" title="${escapeHtml(t.step || t.status)}">${statusIcon(t.status)}</div>
    </div>
    ${errorBlock}
  </div>`;
}

/* ---------- события в режиме draft ---------- */

let langDetectTimers = {};

function wireDraftRowEvents() {
  document.querySelectorAll('[data-action="remove-row"]').forEach((btn) => {
    btn.onclick = () => {
      const id = Number(btn.closest(".task").dataset.rowId);
      delete cselRegistry[`lang-${id}`];
      state.draftRows = state.draftRows.filter((r) => r.id !== id);
      renderQueue();
      updateStartEnabled();
    };
  });

  document.querySelectorAll(".task[data-row-id]").forEach((card) => {
    const id = Number(card.dataset.rowId);
    const row = state.draftRows.find((r) => r.id === id);
    if (!row) return;

    const textEl = card.querySelector('[data-field="text"]');
    textEl.oninput = () => {
      row.text = textEl.value;
      autoGrow(textEl);
      updateStartEnabled();
      clearTimeout(langDetectTimers[id]);
      langDetectTimers[id] = setTimeout(() => detectLanguageForRow(row), 500);
    };

    const nameEl = card.querySelector('[data-field="name"]');
    nameEl.oninput = () => { row.projectName = nameEl.value; };

    const audioEl = card.querySelector('[data-field="audio"]');
    audioEl.onchange = () => {
      if (audioEl.files && audioEl.files[0]) setRowAudio(row, audioEl.files[0]);
    };

    const dropZone = card.querySelector('[data-action="audio-drop"]');
    ["dragenter", "dragover"].forEach((ev) => dropZone.addEventListener(ev, (e) => {
      e.preventDefault(); dropZone.classList.add("drag-over");
    }));
    ["dragleave", "dragend"].forEach((ev) => dropZone.addEventListener(ev, () => {
      dropZone.classList.remove("drag-over");
    }));
    dropZone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
      const file = e.dataTransfer.files && e.dataTransfer.files[0];
      if (file) setRowAudio(row, file);
    });
  });
}

function setRowAudio(row, file) {
  row.audioFile = file;
  renderQueue();
  updateStartEnabled();
}

async function detectLanguageForRow(row) {
  if (row.languageTouched) return; // юзер уже выбрал язык руками — не перетираем
  if (!row.text.trim()) return;
  try {
    const res = await api.post("/api/detect_language", { text: row.text });
    if (res.language && !row.languageTouched) {
      row.language = res.language;
      const st = cselRegistry[`lang-${row.id}`];
      if (st) { st.value = row.language; cselRender(`lang-${row.id}`); }
    }
  } catch (e) { /* молча — автоопределение не критично, останется "auto" */ }
}

function wireBackendTaskEvents() {
  document.querySelectorAll('[data-action="save-log"]').forEach((btn) => {
    btn.onclick = () => {
      const logPath = decodeURIComponent(btn.dataset.log);
      if (!logPath) return;
      const a = document.createElement("a");
      a.href = `/api/log?path=${encodeURIComponent(logPath)}`;
      a.download = "";
      document.body.appendChild(a);
      a.click();
      a.remove();
    };
  });
}

/* ---------- footer / старт-стоп ---------- */

function updateStartEnabled() {
  const startBtn = document.getElementById("startBtn");
  if (state.mode !== "draft") { startBtn.disabled = true; return; }
  const ready = state.draftRows.some((r) => r.text.trim() && r.audioFile);
  startBtn.disabled = !ready;
}

function renderFooter() {
  const label = document.getElementById("progressLabel");
  const pct = document.getElementById("progressPct");
  const fill = document.getElementById("progressFill");
  const startBtn = document.getElementById("startBtn");
  const stopBtn = document.getElementById("stopBtn");

  if (state.mode === "draft") {
    label.textContent = state.draftRows.length ? `${state.draftRows.length} задач${state.draftRows.length === 1 ? "а" : "и"} в очереди` : "Очередь пуста";
    pct.textContent = "";
    fill.style.width = "0%";
    stopBtn.disabled = true;
    updateStartEnabled();
    return;
  }

  const p = (state.backendState && state.backendState.progress) || {};
  const total = p.total || 0;
  const idx = p.task_index || 0;
  label.textContent = total ? `Задача ${idx}/${total}: ${p.message || ""}` : (p.message || "");
  pct.textContent = p.percent != null ? `${Math.round(p.percent)}%` : "";
  fill.style.width = `${p.percent || 0}%`;

  const running = state.backendState && state.backendState.running;
  startBtn.disabled = true;
  stopBtn.disabled = !running;
}

/* ---------- CapCut pill ---------- */

function renderCapcutPill() {
  const pill = document.getElementById("capcutPill");
  const text = document.getElementById("capcutPillText");
  const iconEl = document.getElementById("capcutPillIcon");
  const cc = state.backendState && state.backendState.capcut;
  if (!cc) return;
  if (cc.found) {
    pill.classList.remove("warn"); pill.classList.add("ok");
    text.textContent = "CapCut найден";
    iconEl.innerHTML = ICONS["check-circle"] || "";
    pill.onclick = null;
  } else {
    pill.classList.remove("ok"); pill.classList.add("warn");
    text.textContent = "Папка CapCut не найдена";
    iconEl.innerHTML = ICONS["warning"] || "";
    pill.onclick = openSettings;
  }
}

/* ---------- настройки ---------- */

function openSettings() {
  const cc = (state.backendState && state.backendState.capcut) || {};
  const s = state.settings || {};
  const root = document.getElementById("overlayRoot");

  cselRegistry["model"] = {
    open: false, search: "", searchable: false,
    options: (window.MODEL_CHOICES || []).map((m) => ({ value: m.value, label: m.label })),
    value: s.model_size,
    onChange: (v) => api.post("/api/settings", { model_size: v }),
  };

  root.innerHTML = `
  <div class="overlay" id="settingsOverlay">
    <div class="panel">
      <div class="panel-title">Настройки <button class="icon-btn" id="closeSettings">${iconSpan("close")}</button></div>

      <div class="field">
        <label>Папка проектов CapCut</label>
        <div class="folder-row">
          <input type="text" id="folderInput" value="${escapeHtml(cc.folder || "")}" placeholder="com.lveditor.draft">
          <button class="icon-btn" id="pickFolder" title="Выбрать папку">${iconSpan("folder")}</button>
          <button class="icon-btn" id="saveFolder" title="Сохранить">${iconSpan("check")}</button>
        </div>
        ${!cc.found ? `<div class="hint warn-text">${escapeHtml(cc.instructions || "")}</div>` : `<div class="hint">Определено автоматически.</div>`}
      </div>

      <div class="field">
        <label>Модель распознавания</label>
        ${cselMount("model", cselRegistry["model"])}
      </div>

      <div class="field">
        <div class="switch-row">
          <label style="margin-bottom:0">Автооткрытие CapCut после обработки</label>
          <label class="switch">
            <input type="checkbox" id="autoReopenToggle" ${s.auto_reopen_capcut ? "checked" : ""}>
            <span class="switch-track"></span>
          </label>
        </div>
        <div class="hint">CapCut перед обработкой всегда закрывается сам (иначе он может затереть общий файл со списком проектов во время записи). Этот тумблер — только про то, открывать ли его обратно, когда вся очередь обработана.</div>
      </div>

    </div>
  </div>`;
  applyIcons(root);
  cselRender("model");

  document.getElementById("closeSettings").onclick = closeSettings;
  document.getElementById("settingsOverlay").onclick = (e) => { if (e.target.id === "settingsOverlay") closeSettings(); };

  document.getElementById("saveFolder").onclick = async () => {
    const path = document.getElementById("folderInput").value.trim();
    const res = await api.post("/api/capcut/folder", { path });
    if (res.ok) openSettings();
    else alert(res.error || "Не удалось сохранить путь");
  };

  document.getElementById("pickFolder").onclick = async () => {
    if (window.pywebview && window.pywebview.api && window.pywebview.api.pick_folder) {
      const picked = await window.pywebview.api.pick_folder();
      if (picked) {
        document.getElementById("folderInput").value = picked;
        const res = await api.post("/api/capcut/folder", { path: picked });
        if (res.ok) openSettings();
        else alert(res.error || "Не удалось сохранить путь");
      }
    } else {
      alert("Нативный диалог выбора папки недоступен вне приложения — впиши путь вручную.");
    }
  };

  document.getElementById("autoReopenToggle").onchange = (e) => {
    api.post("/api/settings", { auto_reopen_capcut: e.target.checked });
  };
}

function closeSettings() {
  delete cselRegistry["model"];
  document.getElementById("overlayRoot").innerHTML = "";
}

/* ---------- setup (первый запуск) ---------- */

async function runSetupFlow() {
  const root = document.getElementById("overlayRoot");
  const draw = (status) => {
    root.innerHTML = `
    <div class="setup-screen">
      <div style="text-align:center">
        <div class="setup-title">Готовим CapSync</div>
        <div class="setup-sub">Первый запуск — ставим зависимости распознавания речи</div>
      </div>
      <div class="setup-steps">
        ${status.steps.map((s) => `
          <div class="setup-step ${s.status}">
            ${s.status === "done" ? iconSpan("check") : s.status === "error" ? iconSpan("warning") : s.status === "running" ? iconSpan("spinner", "spin") : iconSpan("close")}
            <div>
              <div class="setup-step-label">${escapeHtml(s.label)}</div>
              ${s.detail ? `<div class="setup-step-detail">${escapeHtml(s.detail)}</div>` : ""}
            </div>
          </div>`).join("")}
      </div>
      <div class="progress-track setup-progress"><div class="progress-fill" style="width:${stepsPercent(status)}%"></div></div>
      ${status.overall === "error" ? `<button class="btn btn-primary setup-retry" id="retrySetup">${iconSpan("play")} Повторить</button>` : ""}
    </div>`;
    applyIcons(root);
    const retry = document.getElementById("retrySetup");
    if (retry) retry.onclick = () => { api.post("/api/setup/run"); poll(); };
  };

  function stepsPercent(status) {
    const done = status.steps.filter((s) => s.status === "done").length;
    return Math.round((done / status.steps.length) * 100);
  }

  let status = await api.get("/api/setup/status");
  draw(status);
  if (status.overall === "pending") {
    await api.post("/api/setup/run");
  }

  function poll() {
    api.get("/api/setup/status").then((s) => {
      draw(s);
      if (s.overall === "done") { closeSettings(); return; }
      if (s.overall === "error") return;
      setTimeout(poll, 700);
    });
  }
  poll();

  return new Promise((resolve) => {
    const check = setInterval(async () => {
      const s = await api.get("/api/setup/status");
      if (s.overall === "done") { clearInterval(check); resolve(); }
    }, 700);
  });
}

/* ---------- старт / стоп ---------- */

async function startQueue() {
  const rows = state.draftRows.filter((r) => r.text.trim() && r.audioFile);
  if (!rows.length) return;

  await api.del("/api/tasks"); // чистим хвост прошлого прогона

  for (const row of rows) {
    const fd = new FormData();
    fd.append("text", row.text.trim());
    fd.append("project_name", row.projectName.trim());
    fd.append("language", row.language || "auto");
    fd.append("audio", row.audioFile);
    await api.postForm("/api/tasks", fd);
  }

  state.mode = "running";
  state.draftRows.forEach((r) => delete cselRegistry[`lang-${r.id}`]);
  state.draftRows = [];
  await api.post("/api/start");
  renderQueue();
  renderFooter();
}

async function stopQueue() {
  await api.post("/api/stop");
}

/* ---------- поллинг основного состояния ---------- */

async function pollState() {
  try {
    const s = await api.get("/api/state");
    state.backendState = s;
    state.settings = s.settings;

    const wasRunning = state.mode === "running";
    if (s.running) {
      state.mode = "running";
      renderQueue();
      renderFooter();
    } else if (wasRunning) {
      state.mode = "finished";
      renderQueue();
      renderFooter();
    }
    renderCapcutPill();
  } catch (e) {
    // сервер не отвечает — молча пробуем снова на следующем тике
  }
  setTimeout(pollState, 500);
}

/* ---------- добавление задачи (хэндлит переход finished -> draft) ---------- */

async function onAddTask() {
  if (state.mode === "finished") {
    await api.del("/api/tasks");
    state.mode = "draft";
    state.draftRows = [];
  }
  state.draftRows.push(newDraftRow());
  renderQueue();
  renderFooter();
}

/* ---------- boot ---------- */

async function boot() {
  await loadIcons();

  const setupStatus = await api.get("/api/setup/status");
  if (setupStatus.overall !== "done") {
    await runSetupFlow();
  }

  const [langsData, settings] = await Promise.all([
    api.get("/api/langs"),
    api.get("/api/settings"),
  ]);
  state.langs = langsData;
  state.settings = settings;
  window.MODEL_CHOICES = [
    { value: "tiny", label: "tiny — самый быстрый, грубые тайминги" },
    { value: "small", label: "small — быстро, средняя точность" },
    { value: "medium", label: "medium — баланс скорости и точности" },
    { value: "large-v3", label: "large-v3 — максимальная точность (рекомендовано)" },
    { value: "large-v3-turbo", label: "large-v3-turbo — почти как large-v3, но быстрее" },
  ];

  state.draftRows = [newDraftRow()];
  renderQueue();
  renderFooter();

  document.getElementById("addTaskBtn").onclick = onAddTask;
  document.getElementById("startBtn").onclick = startQueue;
  document.getElementById("stopBtn").onclick = stopQueue;
  document.getElementById("settingsBtn").onclick = openSettings;

  pollState();
}

boot();
