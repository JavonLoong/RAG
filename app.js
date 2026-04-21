const API_BASE = (window.location.protocol === "file:" || window.location.hostname.endsWith("github.io")) ? "http://localhost:8000" : "";

const SOURCE_LABELS = {
  PDF: "PDF",
  Text: "文本",
  JSON: "JSON",
  Markdown: "Markdown",
  CSV: "CSV",
  TSV: "TSV",
  DOCX: "DOCX",
  Log: "日志",
  Other: "其他"
};

const SOURCE_COLORS = {
  PDF: "rgba(0, 47, 167, 0.92)",
  Text: "rgba(0, 47, 167, 0.68)",
  JSON: "rgba(0, 47, 167, 0.42)",
  Markdown: "rgba(15, 98, 254, 0.72)",
  CSV: "rgba(37, 99, 235, 0.54)",
  TSV: "rgba(59, 130, 246, 0.42)",
  DOCX: "rgba(37, 99, 235, 0.82)",
  Log: "rgba(15, 23, 42, 0.28)",
  Other: "rgba(17, 24, 39, 0.16)"
};

const BENCHMARK_CARDS = [
  { key: "insert_seconds", label: "写入耗时", icon: "lucide:clock-3", formatter: (value) => `${formatDecimal(value, 3)} s` },
  { key: "insert_docs_per_second", label: "写入吞吐", icon: "lucide:database", formatter: (value) => `${formatDecimal(value, 2)} docs/s` },
  { key: "query_seconds", label: "查询耗时", icon: "lucide:timer-reset", formatter: (value) => `${formatDecimal(value, 3)} s` },
  { key: "query_qps", label: "检索 QPS", icon: "lucide:bar-chart-3", formatter: (value) => `${formatDecimal(value, 2)} qps` },
  { key: "avg_query_latency_ms", label: "平均延迟", icon: "lucide:activity", formatter: (value) => `${formatDecimal(value, 3)} ms` },
  { key: "p95_query_latency_ms", label: "P95 延迟", icon: "lucide:gauge", formatter: (value) => `${formatDecimal(value, 3)} ms` },
  { key: "embedding_backend", label: "向量后端", icon: "lucide:workflow", formatter: (value) => String(value || "-") },
  { key: "embedding_model", label: "模型标识", icon: "lucide:database-zap", formatter: (value) => String(value || "-") }
];

const SUPPORTED_EXTENSIONS = new Set(["json", "pdf", "docx", "txt", "md", "markdown", "csv", "tsv", "log"]);

const state = {
  online: false,
  version: "",
  page: "overview",
  stats: null,
  primaryCollection: "",
  primaryStats: null,
  uploads: [],
  pendingUploads: [],
  processedUploads: [],
  selectedUploads: new Set(),
  selectedProcessedUploads: new Set(),
  processedEditMode: false,
  lastProcess: null,
  lastSearch: null,
  benchmark: null,
  activity: [],
  timeline: [],
  expandedResults: new Set(),
  trendMode: "balance",
  activityFilter: "all",
  toastTimer: null
};

const $ = (id) => document.getElementById(id);

let els = {};

function resolveEls() {
  els = {
    sidebar: $("sidebar"),
    sidebarToggle: $("sidebarToggle"),
    sidebarToggleIcon: $("sidebarToggleIcon"),
    navList: $("navList"),
    pages: Array.from(document.querySelectorAll(".page")),
    refreshBtn: $("refreshBtn"),
    refreshStamp: $("refreshStamp"),
    statusText: $("statusText"),
    sysStatus: $("sysStatus"),
    statusPill: $("statusPill"),
    globalSearchForm: $("globalSearchForm"),
    globalSearchInput: $("globalSearchInput"),
    collectionSummaryPill: $("collectionSummaryPill"),
    collectionSpectrum: $("collectionSpectrum"),
    collList: $("collList"),
    trendSummaryPill: $("trendSummaryPill"),
    trendModeGroup: $("trendModeGroup"),
    trendChart: $("trendChart"),
    miniThroughput: $("miniThroughput"),
    miniPrecision: $("miniPrecision"),
    activityFilterGroup: $("activityFilterGroup"),
    activityFeed: $("activityFeed"),
    searchPulse: $("searchPulse"),
    statDocs: $("statDocs"),
    sparkDocs: $("sparkDocs"),
    docsPdf: $("docsPdf"),
    docsText: $("docsText"),
    docsJson: $("docsJson"),
    docsOther: $("docsOther"),
    statTokens: $("statTokens"),
    sparkTokens: $("sparkTokens"),
    statSize: $("statSize"),
    statDim: $("statDim"),
    statRecordCount: $("statRecordCount"),
    statChunkCount: $("statChunkCount"),
    statColls: $("statColls"),
    sparkColls: $("sparkColls"),
    statPrimaryCollection: $("statPrimaryCollection"),
    statSuccessFiles: $("statSuccessFiles"),
    statFailedFiles: $("statFailedFiles"),
    statStorageLive: $("statStorageLive"),
    statLatency: $("statLatency"),
    sparkLatency: $("sparkLatency"),
    statLastResults: $("statLastResults"),
    statP95: $("statP95"),
    statPrecision: $("statPrecision"),
    statQuality: $("statQuality"),
    dropZone: $("dropZone"),
    pickFilesButton: $("pickFilesButton"),
    pickFolderButton: $("pickFolderButton"),
    dropBrowseButton: $("dropBrowseButton"),
    dropFolderButton: $("dropFolderButton"),
    fileInput: $("fileInput"),
    folderInput: $("folderInput"),
    uploadQueueMeta: $("uploadQueueMeta"),
    reloadQueueButton: $("reloadQueueButton"),
    selectAllUploads: $("selectAllUploads"),
    clearUploadSelection: $("clearUploadSelection"),
    btnProcess: $("btnProcess"),
    processProgress: $("processProgress"),
    processFill: $("processFill"),
    processLog: $("processLog"),
    queueCountPill: $("queueCountPill"),
    queueList: $("queueList"),
    processedMeta: $("processedMeta"),
    processedCountPill: $("processedCountPill"),
    processedEditButton: $("processedEditButton"),
    processedDeleteButton: $("processedDeleteButton"),
    processedList: $("processedList"),
    qualityReport: $("qualityReport"),
    searchInput: $("searchInput"),
    searchTopK: $("searchTopK"),
    btnSearch: $("btnSearch"),
    searchMeta: $("searchMeta"),
    searchResults: $("searchResults"),
    benchDocs: $("benchDocs"),
    benchBatch: $("benchBatch"),
    benchQueries: $("benchQueries"),
    benchTopK: $("benchTopK"),
    benchFill: $("benchFill"),
    btnBench: $("btnBench"),
    benchLog: $("benchLog"),
    benchEmpty: $("benchEmpty"),
    benchGrid: $("benchGrid"),
    toast: $("toast")
  };
}
function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(Number(value || 0));
}

function formatDecimal(value, digits = 2) {
  const numeric = Number(value || 0);
  return Number.isFinite(numeric) ? numeric.toFixed(digits) : "0.00";
}

function formatPercent(value, digits = 1) {
  const numeric = Number(value || 0);
  return `${(numeric * 100).toFixed(digits)}%`;
}

function formatMegabytes(value) {
  return `${formatDecimal(value || 0, 2)} MB`;
}

function normalizeTime(value) {
  const numeric = Number(value || 0);
  if (!numeric) return null;
  return numeric < 1e12 ? numeric * 1000 : numeric;
}

function formatClock(value) {
  const time = normalizeTime(value);
  if (!time) return "--";
  return new Date(time).toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

function snapshotClock() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false
  });
}

function normalizeKind(kind) {
  const raw = String(kind || "").trim();
  if (!raw) return "Other";
  const normalized = raw.toLowerCase();
  if (normalized === "pdf") return "PDF";
  if (["text", "txt", "plain"].includes(normalized)) return "Text";
  if (normalized === "json") return "JSON";
  if (["markdown", "md"].includes(normalized)) return "Markdown";
  if (normalized === "csv") return "CSV";
  if (normalized === "tsv") return "TSV";
  if (normalized === "docx") return "DOCX";
  if (normalized === "log") return "Log";
  return raw in SOURCE_LABELS ? raw : "Other";
}

function kindLabel(kind) {
  return SOURCE_LABELS[normalizeKind(kind)] || SOURCE_LABELS.Other;
}

function sourceColor(kind) {
  return SOURCE_COLORS[normalizeKind(kind)] || SOURCE_COLORS.Other;
}

function iconMarkup(icon, className = "") {
  return icon ? `<iconify-icon class="${className}" icon="${icon}"></iconify-icon>` : "";
}

function summarizeName(filename) {
  return String(filename || "").replaceAll("__", " / ");
}

function uploadDisplayName(itemOrFilename) {
  if (typeof itemOrFilename === "string") {
    const found = (state.uploads || []).find((item) => item.filename === itemOrFilename);
    return found?.display_name ? String(found.display_name) : summarizeName(itemOrFilename);
  }
  if (itemOrFilename?.display_name) return String(itemOrFilename.display_name);
  return summarizeName(itemOrFilename?.filename || "");
}

function splitUploadPath(value) {
  const normalized = String(value || "").replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  return {
    file: parts.length ? parts[parts.length - 1] : normalized,
    folder: parts.length > 1 ? parts.slice(0, -1).join(" / ") : "根目录"
  };
}

function statusTagMarkup(status) {
  const normalized = status === "processed" ? "processed" : "uploaded";
  const label = normalized === "processed" ? "已处理" : "待处理";
  const cls = normalized === "processed" ? "status-tag success" : "status-tag";
  return `<span class="${cls}">${label}</span>`;
}

function getPendingUploads() {
  return Array.isArray(state.pendingUploads) ? state.pendingUploads : [];
}

function getProcessedUploads() {
  return Array.isArray(state.processedUploads) ? state.processedUploads : [];
}

function syncUploadSelections() {
  const pendingNames = new Set(getPendingUploads().map((item) => item.filename));
  const processedNames = new Set(getProcessedUploads().map((item) => item.filename));
  state.selectedUploads = new Set(Array.from(state.selectedUploads).filter((name) => pendingNames.has(name)));
  state.selectedProcessedUploads = new Set(Array.from(state.selectedProcessedUploads).filter((name) => processedNames.has(name)));
  if (!getProcessedUploads().length) {
    state.processedEditMode = false;
    state.selectedProcessedUploads.clear();
  }
}
function averageScore(results) {
  if (!Array.isArray(results) || !results.length) return 0;
  return results.reduce((sum, item) => sum + Number(item?.score || 0), 0) / results.length;
}

function choosePrimaryCollection(collections) {
  const list = Array.isArray(collections) ? collections.slice() : [];
  if (!list.length) return "";
  if (state.primaryCollection && list.some((item) => item.name === state.primaryCollection)) {
    return state.primaryCollection;
  }
  const nonBenchmark = list
    .filter((item) => !String(item.name || "").startsWith("benchmark"))
    .sort((left, right) => Number(right.count || 0) - Number(left.count || 0));
  if (nonBenchmark.length) return nonBenchmark[0].name;
  list.sort((left, right) => Number(right.count || 0) - Number(left.count || 0));
  return list[0]?.name || "";
}

function statsBreakdown(stats) {
  const raw = stats?.source_type_breakdown || {};
  const breakdown = { PDF: 0, Text: 0, JSON: 0, Other: 0 };
  Object.entries(raw).forEach(([key, value]) => {
    const kind = normalizeKind(key);
    if (kind === "PDF") breakdown.PDF += Number(value || 0);
    else if (kind === "Text" || kind === "Markdown" || kind === "DOCX" || kind === "Log") breakdown.Text += Number(value || 0);
    else if (kind === "JSON") breakdown.JSON += Number(value || 0);
    else breakdown.Other += Number(value || 0);
  });
  return breakdown;
}

function dotClass(level) {
  return level === "success" ? "status-dot" : `status-dot ${level}`;
}

function setStatusLevel(level) {
  const pillDot = els.statusPill?.querySelector(".status-dot");
  if (els.sysStatus) els.sysStatus.className = dotClass(level);
  if (pillDot) pillDot.className = dotClass(level);
}

function showToast(message, level = "success") {
  if (!els.toast) return;
  clearTimeout(state.toastTimer);
  els.toast.textContent = message;
  els.toast.className = `toast ${level} show`.trim();
  state.toastTimer = window.setTimeout(() => {
    els.toast.className = "toast";
  }, 2800);
}

function addActivity(level, title, detail) {
  state.activity.unshift({
    id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    level,
    title,
    detail,
    at: Date.now()
  });
  state.activity = state.activity.slice(0, 30);
  renderActivityFeed();
}

function rememberTimeline(reason) {
  if (!state.stats) return;
  const breakdown = statsBreakdown(state.stats);
  const snapshot = {
    reason,
    label: snapshotClock(),
    docs: Number(state.stats.total_documents || 0),
    tokens: Number(state.stats.total_tokens_estimate || 0),
    collections: Number((state.stats.collections || []).length),
    latency: Number(state.lastSearch?.latency_ms || state.benchmark?.avg_query_latency_ms || 0),
    pdf: Number(breakdown.PDF || 0),
    text: Number(breakdown.Text || 0),
    json: Number(breakdown.JSON || 0),
    other: Number(breakdown.Other || 0)
  };

  const last = state.timeline[state.timeline.length - 1];
  if (
    last &&
    last.docs === snapshot.docs &&
    last.tokens === snapshot.tokens &&
    last.collections === snapshot.collections &&
    Math.abs(last.latency - snapshot.latency) < 0.001 &&
    last.reason === snapshot.reason
  ) {
    return;
  }

  state.timeline.push(snapshot);
  state.timeline = state.timeline.slice(-10);
}

function apiUrl(path) {
  return `${API_BASE}${path}`;
}

async function requestJson(path, options = {}, timeoutMs = 120000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(apiUrl(path), {
      ...options,
      signal: controller.signal
    });
    const isJson = response.headers.get("content-type")?.includes("application/json");
    const payload = isJson ? await response.json() : await response.text();
    if (!response.ok) {
      const detail = typeof payload === "object" ? (payload.detail || payload.message || JSON.stringify(payload)) : payload;
      throw new Error(detail || `请求失败: ${response.status}`);
    }
    return payload;
  } finally {
    window.clearTimeout(timer);
  }
}

function renderEmpty(container, message) {
  if (!container) return;
  container.innerHTML = `<div class="empty-state">${escapeHtml(message)}</div>`;
}

function setPage(page) {
  state.page = page;
  els.pages.forEach((element) => {
    element.classList.toggle("active", element.id === `page-${page}`);
  });
  els.navList?.querySelectorAll(".nav-item").forEach((button) => {
    button.classList.toggle("active", button.dataset.page === page);
  });
}

function syncSidebarToggleIcon() {
  if (!els.sidebarToggleIcon || !els.sidebar) return;
  els.sidebarToggleIcon.setAttribute(
    "icon",
    els.sidebar.classList.contains("is-collapsed") ? "lucide:chevrons-right" : "lucide:chevrons-left"
  );
}

function renderSparkline(svg, values, color) {
  if (!svg) return;
  const points = Array.isArray(values) ? values : [];
  if (!points.length) {
    svg.innerHTML = "";
    return;
  }
  const width = 96;
  const height = 32;
  const max = Math.max(...points, 1);
  const min = Math.min(...points, 0);
  const span = max - min || 1;
  const coordinates = points.map((value, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - ((value - min) / span) * (height - 6) - 3;
    return `${x},${y}`;
  }).join(" ");
  svg.innerHTML = `
    <polyline
      points="${coordinates}"
      fill="none"
      stroke="${color}"
      stroke-width="3"
      stroke-linecap="round"
      stroke-linejoin="round"
    ></polyline>
  `;
}

function renderStatus() {
  if (!els.statusText || !els.refreshStamp) return;
  if (state.online) {
    els.statusText.textContent = `后端在线${state.version ? ` · v${state.version}` : ""}，上传与检索链路可用`;
    els.refreshStamp.textContent = `最近同步 ${snapshotClock()}`;
    setStatusLevel("success");
  } else {
    els.statusText.textContent = "后端未连接，请先启动 http://localhost:8000";
    els.refreshStamp.textContent = "等待后端连接";
    setStatusLevel("danger");
  }
}

function renderCollectionSpectrum() {
  if (!els.collectionSpectrum || !els.collectionSummaryPill) return;
  const collections = state.stats?.collections || [];
  if (!collections.length) {
    els.collectionSummaryPill.textContent = "暂无集合";
    renderEmpty(els.collectionSpectrum, "当前还没有向量集合，先去上传并处理文件。");
    return;
  }

  const total = collections.reduce((sum, item) => sum + Number(item.count || 0), 0) || 1;
  els.collectionSummaryPill.textContent = `${collections.length} 个集合`;

  const bars = collections.map((item) => {
    const count = Number(item.count || 0);
    const width = Math.max(8, Math.round((count / total) * 100));
    const active = item.name === state.primaryCollection;
    return `
      <div
        title="${escapeHtml(item.name)}: ${formatNumber(count)}"
        style="flex:${width} 1 0;min-width:28px;height:16px;border-radius:999px;background:${active ? "rgba(0, 47, 167, 0.92)" : "rgba(15, 23, 42, 0.16)"};"
      ></div>
    `;
  }).join("");

  const labels = collections.map((item) => `
    <span>
      ${escapeHtml(item.name)}
      ${item.name === state.primaryCollection ? "· 默认" : ""}
    </span>
  `).join("");

  els.collectionSpectrum.innerHTML = `
    <div style="display:flex;gap:8px;align-items:center;">${bars}</div>
    <div class="metric-subgrid">${labels}</div>
  `;
}

function renderCollectionList() {
  if (!els.collList) return;
  const collections = state.stats?.collections || [];
  if (!collections.length) {
    renderEmpty(els.collList, "还没有可管理的集合。");
    return;
  }

  els.collList.innerHTML = collections.map((item) => {
    const typeCounts = item.source_type_counts || {};
    const meta = Object.entries(typeCounts)
      .slice(0, 4)
      .map(([kind, count]) => `<span>${escapeHtml(kindLabel(kind))}: ${formatNumber(count)}</span>`)
      .join("");

    return `
      <article class="collection-item">
        <div class="collection-head">
          <div>
            <div class="queue-name">${escapeHtml(item.name)}</div>
            <p>${formatNumber(item.count || 0)} 个向量片段 · 约 ${formatNumber(item.estimated_tokens || 0)} tokens</p>
          </div>
          <span class="pill">${item.name === state.primaryCollection ? "默认集合" : `${formatNumber((item.sources || []).length)} 个来源`}</span>
        </div>
        <div class="queue-meta">
          <span>估算字符 ${formatNumber(item.estimated_chars || 0)}</span>
          <span>${meta || "待补充来源信息"}</span>
        </div>
        <div class="queue-actions">
          <button class="ghost-btn" type="button" data-set-collection="${escapeHtml(item.name)}">设为默认</button>
          <button class="ghost-btn" type="button" data-delete-collection="${escapeHtml(item.name)}">删除集合</button>
        </div>
      </article>
    `;
  }).join("");
}

function renderTrendChart() {
  if (!els.trendChart || !els.trendSummaryPill) return;
  if (!state.timeline.length) {
    els.trendSummaryPill.textContent = "等待数据";
    renderEmpty(els.trendChart, "刷新统计、检索或压测后，这里会显示会话趋势。");
    renderSparkline(els.sparkDocs, [], "#002fa7");
    renderSparkline(els.sparkTokens, [], "#1d4ed8");
    renderSparkline(els.sparkColls, [], "#0f172a");
    renderSparkline(els.sparkLatency, [], "#d97706");
    return;
  }

  const timeline = state.timeline.slice(-8);
  const docsValues = timeline.map((item) => item.docs);
  const tokenValues = timeline.map((item) => item.tokens);
  const collectionValues = timeline.map((item) => item.collections);
  const latencyValues = timeline.map((item) => item.latency);

  renderSparkline(els.sparkDocs, docsValues, "#002fa7");
  renderSparkline(els.sparkTokens, tokenValues, "#1d4ed8");
  renderSparkline(els.sparkColls, collectionValues, "#0f172a");
  renderSparkline(els.sparkLatency, latencyValues, "#d97706");

  let series;
  let summary;
  if (state.trendMode === "volume") {
    series = timeline.map((item) => item.docs);
    summary = "文档增量";
  } else if (state.trendMode === "latency") {
    series = timeline.map((item) => item.latency);
    summary = "检索延迟";
  } else {
    series = timeline.map((item) => item.tokens);
    summary = "向量规模";
  }

  els.trendSummaryPill.textContent = summary;
  const max = Math.max(...series, 1);
  const bars = timeline.map((item, index) => {
    const value = series[index];
    const height = Math.max(18, Math.round((value / max) * 160));
    const label = state.trendMode === "latency"
      ? `${formatDecimal(value, 2)} ms`
      : state.trendMode === "volume"
        ? `${formatNumber(value)} 条`
        : `${formatNumber(value)} tk`;

    return `
      <div style="display:grid;gap:10px;align-content:end;">
        <div style="height:180px;display:flex;align-items:flex-end;">
          <div style="width:100%;min-width:36px;height:${height}px;border-radius:14px 14px 10px 10px;background:linear-gradient(180deg, rgba(0,47,167,0.92), rgba(15,98,254,0.36));"></div>
        </div>
        <div class="queue-meta">
          <span>${escapeHtml(item.label)}</span>
          <span>${escapeHtml(label)}</span>
        </div>
      </div>
    `;
  }).join("");

  els.trendChart.innerHTML = `
    <div style="display:grid;grid-template-columns:repeat(${timeline.length}, minmax(48px, 1fr));gap:14px;align-items:end;">
      ${bars}
    </div>
  `;
}

function renderActivityFeed() {
  if (!els.activityFeed) return;
  const items = state.activityFilter === "all"
    ? state.activity
    : state.activity.filter((item) => item.level === state.activityFilter);
  if (!items.length) {
    renderEmpty(els.activityFeed, "当前没有活动日志。");
    return;
  }

  els.activityFeed.innerHTML = items.map((item) => `
    <article class="activity-item">
      <div class="activity-head">
        <span class="${dotClass(item.level)}"></span>
        <div class="activity-title">${escapeHtml(item.title)}</div>
      </div>
      <p>${escapeHtml(item.detail)}</p>
      <div class="activity-meta">
        <span>${formatClock(item.at)}</span>
        <span>${item.level === "success" ? "成功" : item.level === "warning" ? "提醒" : "异常"}</span>
      </div>
    </article>
  `).join("");
}

function renderSummaryMetrics() {
  const stats = state.stats || {};
  const primary = state.primaryStats || {};
  const breakdown = statsBreakdown(stats);
  const searchResults = state.lastSearch?.results || [];
  const searchScore = averageScore(searchResults);
  const throughput = state.benchmark?.insert_docs_per_second
    ? `${formatDecimal(state.benchmark.insert_docs_per_second, 1)} docs/s`
    : state.lastProcess?.chunks_written && state.lastProcess?.elapsed_s
      ? `${formatDecimal(Number(state.lastProcess.chunks_written) / Math.max(Number(state.lastProcess.elapsed_s), 1), 1)} chunks/s`
      : "--";

  if (els.statDocs) els.statDocs.textContent = formatNumber(stats.total_documents || 0);
  if (els.docsPdf) els.docsPdf.textContent = `PDF: ${formatNumber(breakdown.PDF || 0)}`;
  if (els.docsText) els.docsText.textContent = `文本: ${formatNumber(breakdown.Text || 0)}`;
  if (els.docsJson) els.docsJson.textContent = `JSON: ${formatNumber(breakdown.JSON || 0)}`;
  if (els.docsOther) els.docsOther.textContent = `其他: ${formatNumber(breakdown.Other || 0)}`;
  if (els.statTokens) els.statTokens.textContent = formatNumber(stats.total_tokens_estimate || 0);
  if (els.statSize) els.statSize.textContent = formatMegabytes(stats.storage_size_mb || 0);
  if (els.statDim) els.statDim.textContent = `${formatNumber(stats.embedding_dim || 0)} 维`;
  if (els.statRecordCount) els.statRecordCount.textContent = `记录: ${formatNumber(primary.record_count || 0)}`;
  if (els.statChunkCount) els.statChunkCount.textContent = `片段: ${formatNumber(primary.chunk_count || 0)}`;
  if (els.statColls) els.statColls.textContent = formatNumber((stats.collections || []).length);
  if (els.statPrimaryCollection) els.statPrimaryCollection.textContent = `当前集合: ${state.primaryCollection || "-"}`;
  if (els.statSuccessFiles) els.statSuccessFiles.textContent = `成功文件: ${formatNumber(state.lastProcess?.files_succeeded || 0)}`;
  if (els.statFailedFiles) els.statFailedFiles.textContent = `失败文件: ${formatNumber(state.lastProcess?.files_failed || 0)}`;
  if (els.statStorageLive) els.statStorageLive.textContent = `实时存储 ${formatMegabytes(stats.storage_size_mb || 0)}`;

  if (els.statLatency) {
    const latency = state.lastSearch?.latency_ms ?? state.benchmark?.avg_query_latency_ms;
    els.statLatency.textContent = Number.isFinite(latency) ? `${formatDecimal(latency, 2)} ms` : "--";
  }
  if (els.statLastResults) els.statLastResults.textContent = `结果数: ${formatNumber(searchResults.length)}`;
  if (els.statP95) {
    const p95 = state.benchmark?.p95_query_latency_ms;
    els.statP95.textContent = `P95: ${Number.isFinite(p95) ? `${formatDecimal(p95, 2)} ms` : "--"}`;
  }
  if (els.statPrecision) els.statPrecision.textContent = `精度: ${searchResults.length ? formatPercent(searchScore, 1) : "--"}`;
  if (els.statQuality) els.statQuality.textContent = state.lastProcess?.quality_report?.issue_count ? `质量告警 ${state.lastProcess.quality_report.issue_count} 条` : "质量监测正常";
  if (els.miniThroughput) els.miniThroughput.textContent = throughput;
  if (els.miniPrecision) els.miniPrecision.textContent = searchResults.length ? formatPercent(searchScore, 1) : "--";
  if (els.searchPulse) els.searchPulse.textContent = searchResults.length ? `${searchResults.length} hits` : (state.online ? "等待检索" : "后端离线");
}

function renderUploads() {
  if (!els.queueList || !els.uploadQueueMeta || !els.queueCountPill) return;

  const uploads = Array.isArray(state.uploads) ? state.uploads : [];
  const pending = getPendingUploads();
  const processed = getProcessedUploads();
  const selectedCount = Array.from(state.selectedUploads).filter((name) => pending.some((item) => item.filename === name)).length;

  els.queueCountPill.textContent = `${formatNumber(uploads.length)} 个文件`;
  if (els.selectAllUploads) els.selectAllUploads.disabled = !pending.length;
  if (els.clearUploadSelection) els.clearUploadSelection.disabled = !selectedCount;
  if (els.btnProcess && els.btnProcess.dataset.busy !== "true") {
    els.btnProcess.disabled = !selectedCount;
  }

  els.uploadQueueMeta.textContent = uploads.length
    ? `上传目录共 ${formatNumber(uploads.length)} 个文件，待处理 ${formatNumber(pending.length)} 个，已处理 ${formatNumber(processed.length)} 个。${selectedCount ? ` 已勾选 ${formatNumber(selectedCount)} 个待处理文件。` : ""}`
    : "上传文件或文件夹后，这里会显示整个上传目录。";

  if (!uploads.length) {
    renderEmpty(els.queueList, "上传后，这里会显示整个上传目录；勾选待处理文件再入库。");
    return;
  }

  els.queueList.innerHTML = uploads.map((item) => {
    const displayName = uploadDisplayName(item);
    const pathInfo = splitUploadPath(displayName);
    const isProcessed = item.status === "processed";
    const isSelected = !isProcessed && state.selectedUploads.has(item.filename);
    const stamp = isProcessed ? (item.processed_at || item.modified) : (item.uploaded_at || item.modified);
    const recordMeta = isProcessed
      ? `${formatNumber(item.last_records || 0)} 条记录 · ${formatNumber(item.last_chunks || 0)} 个片段`
      : "勾选后可加入本次处理";

    return `
      <article class="queue-item ${isSelected ? "is-selected" : ""} ${isProcessed ? "is-processed" : ""}">
        <div class="queue-head">
          <div class="queue-title-row">
            <label class="check-chip ${isProcessed ? "is-disabled" : ""}">
              <input type="checkbox" data-upload-select="${escapeHtml(item.filename)}" ${isSelected ? "checked" : ""} ${isProcessed ? "disabled" : ""}>
              <span></span>
            </label>
            <div>
              <div class="queue-name">${escapeHtml(pathInfo.file)}</div>
              <p>${escapeHtml(pathInfo.folder)} · ${escapeHtml(kindLabel(item.source_kind))} · ${formatDecimal(item.size_kb || 0, 1)} KB</p>
            </div>
          </div>
          <div class="queue-badge-row">
            ${statusTagMarkup(item.status)}
            <span class="pill">${formatClock(stamp)}</span>
          </div>
        </div>
        <div class="queue-meta">
          <span>存储名 ${escapeHtml(item.filename)}</span>
          <span>${recordMeta}</span>
        </div>
        ${item.last_error ? `<div class="queue-hint danger-text">${escapeHtml(item.last_error)}</div>` : ""}
        <div class="queue-actions is-tight">
          ${isProcessed ? "" : `<button class="ghost-btn" type="button" data-delete-upload="${escapeHtml(item.filename)}">移出目录</button>`}
        </div>
      </article>
    `;
  }).join("");
}

function renderProcessedUploads() {
  if (!els.processedList || !els.processedMeta || !els.processedCountPill) return;

  const processed = getProcessedUploads();
  if (!processed.length && state.processedEditMode) {
    state.processedEditMode = false;
    state.selectedProcessedUploads.clear();
  }

  const selectedCount = state.selectedProcessedUploads.size;
  els.processedCountPill.textContent = `${formatNumber(processed.length)} 个文件`;
  els.processedMeta.textContent = processed.length
    ? `这里展示已经完成入库的文件。${state.processedEditMode ? ` 已勾选 ${formatNumber(selectedCount)} 个文件准备删除。` : " 删除时会同步清理对应向量。"}`
    : "处理完成的文件会自动进入这里。";

  if (els.processedEditButton) {
    els.processedEditButton.disabled = !processed.length && !state.processedEditMode;
    els.processedEditButton.innerHTML = `${iconMarkup(state.processedEditMode ? "lucide:x" : "lucide:pencil-line")}<span>${state.processedEditMode ? "完成" : "编辑"}</span>`;
  }
  if (els.processedDeleteButton) {
    els.processedDeleteButton.hidden = !state.processedEditMode;
    els.processedDeleteButton.disabled = !selectedCount;
  }

  if (!processed.length) {
    renderEmpty(els.processedList, "处理完成的文件会显示在这里，和上传目录分开展示。");
    return;
  }

  els.processedList.innerHTML = processed.map((item) => {
    const displayName = uploadDisplayName(item);
    const pathInfo = splitUploadPath(displayName);
    const isSelected = state.selectedProcessedUploads.has(item.filename);

    return `
      <article class="queue-item ${isSelected ? "is-selected" : ""}">
        <div class="queue-head">
          <div class="queue-title-row">
            ${state.processedEditMode ? `
              <label class="check-chip">
                <input type="checkbox" data-processed-select="${escapeHtml(item.filename)}" ${isSelected ? "checked" : ""}>
                <span></span>
              </label>
            ` : ""}
            <div>
              <div class="queue-name">${escapeHtml(pathInfo.file)}</div>
              <p>${escapeHtml(pathInfo.folder)} · ${escapeHtml(kindLabel(item.source_kind))}</p>
            </div>
          </div>
          <div class="queue-badge-row">
            ${statusTagMarkup("processed")}
            <span class="pill">${formatClock(item.processed_at || item.modified)}</span>
          </div>
        </div>
        <div class="queue-meta">
          <span>集合 ${escapeHtml(item.last_collection || "power_equipment")}</span>
          <span>${formatNumber(item.last_records || 0)} 条记录</span>
          <span>${formatNumber(item.last_chunks || 0)} 个片段</span>
        </div>
        <div class="queue-hint">删除时会同步移除该文件及其向量数据。</div>
      </article>
    `;
  }).join("");
}

function renderProcessSummary() {
  if (!els.processLog) return;
  const result = state.lastProcess;
  if (!result) {
    renderEmpty(els.processLog, "勾选待处理文件并完成入库后，这里会显示本次处理摘要。");
    return;
  }

  const summaries = Array.isArray(result.file_summaries) ? result.file_summaries : [];
  const requested = Array.isArray(result.requested_filenames) ? result.requested_filenames : [];
  const skipped = Array.isArray(result.skipped_already_processed) ? result.skipped_already_processed : [];
  const items = [
    `
      <article class="queue-item">
        <div class="queue-head">
          <div>
            <div class="queue-name">本次处理摘要</div>
            <p>${formatNumber(result.records_processed || 0)} 条记录，${formatNumber(result.chunks_written || 0)} 个片段入库</p>
          </div>
          <span class="pill">${formatDecimal(result.elapsed_s || 0, 1)} s</span>
        </div>
        <div class="queue-meta">
          <span>请求 ${formatNumber(requested.length)} 个</span>
          <span>成功 ${formatNumber(result.files_succeeded || 0)} 个</span>
          <span>失败 ${formatNumber(result.files_failed || 0)} 个</span>
          <span>跳过 ${formatNumber(skipped.length)} 个</span>
        </div>
      </article>
    `
  ];

  summaries.forEach((item) => {
    const displayName = uploadDisplayName(item.source_file);
    const pathInfo = splitUploadPath(displayName);
    items.push(`
      <article class="queue-item">
        <div class="queue-head">
          <div>
            <div class="queue-name">${escapeHtml(pathInfo.file)}</div>
            <p>${escapeHtml(pathInfo.folder)} · ${escapeHtml(kindLabel(item.source_kind))} · ${item.status === "ok" ? "提取成功" : "提取失败"}</p>
          </div>
          <span class="pill">${item.status === "ok" ? `${formatNumber(item.records_extracted || 0)} 条` : "error"}</span>
        </div>
        <div class="queue-meta">
          <span>${item.status === "ok" ? "已标记为已处理" : "未写入向量库"}</span>
          <span>${item.status === "ok" ? `记录 ${formatNumber(item.records_extracted || 0)}` : escapeHtml(item.error || "处理失败")}</span>
        </div>
      </article>
    `);
  });

  if (skipped.length) {
    items.push(`
      <article class="queue-item">
        <div class="queue-head">
          <div>
            <div class="queue-name">已跳过文件</div>
            <p>这些文件之前已经处理过，本次不会重复扫描。</p>
          </div>
          <span class="pill">${formatNumber(skipped.length)} 个</span>
        </div>
        <div class="queue-meta">
          <span>${escapeHtml(skipped.map((name) => splitUploadPath(uploadDisplayName(name)).file).slice(0, 6).join(" / ") || "无")}</span>
        </div>
      </article>
    `);
  }

  els.processLog.innerHTML = items.join("");
}

function renderQualityReport() {
  if (!els.qualityReport) return;
  const report = state.lastProcess?.quality_report;
  if (!report) {
    renderEmpty(els.qualityReport, "处理完成后，会显示分块统计和质量问题摘要。");
    return;
  }

  const chunks = report.chunks || {};
  const docs = Array.isArray(report.documents) ? report.documents : [];
  const issues = Array.isArray(report.issues) ? report.issues : [];
  const docItems = docs.slice(0, 4).map((item) => `
    <article class="queue-item">
      <div class="queue-head">
        <div>
          <div class="queue-name">${escapeHtml((item.filenames || []).map(summarizeName).join(" / ") || `doc${item.doc_id}`)}</div>
          <p>${formatNumber(item.block_count || 0)} 个 block</p>
        </div>
        <span class="pill">${formatNumber(item.short_blocks || 0)} 短块</span>
      </div>
      <div class="queue-meta">
        <span>${Object.entries(item.label_distribution || {}).map(([key, value]) => `${key}:${value}`).join(" · ") || "无标签统计"}</span>
      </div>
    </article>
  `).join("");

  const issueItems = issues.slice(0, 4).map((issue) => `<span>${escapeHtml(issue)}</span>`).join("");
  els.qualityReport.innerHTML = `
    <article class="queue-item">
      <div class="queue-head">
        <div>
          <div class="queue-name">分块统计</div>
          <p>平均长度 ${formatNumber(chunks.avg_length || 0)}，最短 ${formatNumber(chunks.min_length || 0)}，最长 ${formatNumber(chunks.max_length || 0)}</p>
        </div>
        <span class="pill">${formatNumber(chunks.total_chunks || 0)} chunks</span>
      </div>
      <div class="queue-meta">
        <span>问题数 ${formatNumber(report.issue_count || 0)}</span>
        <span>${issueItems || "未检测到明显质量问题"}</span>
      </div>
    </article>
    ${docItems || '<div class="empty-state">暂无文档级质量摘要。</div>'}
  `;
}

function renderSearchResults() {
  if (!els.searchMeta || !els.searchResults) return;
  const payload = state.lastSearch;
  if (!payload) {
    els.searchMeta.textContent = "等待检索输入。";
    renderEmpty(els.searchResults, "输入问题后，这里会显示相似片段、来源与得分。");
    return;
  }

  const results = Array.isArray(payload.results) ? payload.results : [];
  const score = averageScore(results);
  els.searchMeta.textContent = [
    `集合 ${payload.collection || state.primaryCollection || "-"}`,
    `延迟 ${formatDecimal(payload.latency_ms || 0, 2)} ms`,
    `结果 ${formatNumber(results.length)}`,
    payload.embedding_backend ? `后端 ${payload.embedding_backend}` : ""
  ].filter(Boolean).join(" · ");

  if (!results.length) {
    renderEmpty(els.searchResults, payload.message || "没有检索到结果。");
    if (els.statPrecision) els.statPrecision.textContent = score ? `精度: ${formatPercent(score, 1)}` : "精度: --";
    return;
  }

  els.searchResults.innerHTML = results.map((item, index) => {
    const key = `${payload.query}-${index}-${item?.metadata?.chunk_index || 0}`;
    const expanded = state.expandedResults.has(key);
    const metadata = item.metadata || {};
    return `
      <article class="result-card ${expanded ? "is-expanded" : ""}">
        <div class="result-head">
          <div>
            <div class="result-title">${escapeHtml(summarizeName(metadata.filename || metadata.source_file || `结果 ${index + 1}`))}</div>
            <div class="result-meta">
              <span>${escapeHtml(kindLabel(metadata.source_kind))}</span>
              <span>score ${formatPercent(item.score || 0, 1)}</span>
              <span>distance ${formatDecimal(item.distance || 0, 4)}</span>
              <span>chunk ${formatNumber(metadata.chunk_index || 0)}</span>
            </div>
          </div>
          <div class="result-score">${formatPercent(item.score || 0, 1)}</div>
        </div>
        <p class="result-body">${escapeHtml(item.text || "")}</p>
        <div class="queue-meta">
          <span>record ${escapeHtml(metadata.record_id || "-")}</span>
          <span>tokens ${formatNumber(metadata.estimated_tokens || 0)}</span>
          <span>pages ${escapeHtml(String(metadata.page_nums || "-"))}</span>
        </div>
        <button class="result-toggle" type="button" data-result-toggle="${escapeHtml(key)}">${expanded ? "收起" : "展开全文"}</button>
      </article>
    `;
  }).join("");
}

function renderBenchmark() {
  if (!els.benchGrid || !els.benchLog || !els.benchEmpty) return;
  const benchmark = state.benchmark;
  if (!benchmark) {
    els.benchLog.textContent = "等待压测开始。";
    els.benchEmpty.style.display = "";
    els.benchGrid.innerHTML = "";
    return;
  }

  els.benchEmpty.style.display = "none";
  els.benchLog.textContent = `集合 ${benchmark.collection} · 写入 ${formatDecimal(benchmark.insert_seconds, 3)} s · 平均延迟 ${formatDecimal(benchmark.avg_query_latency_ms, 3)} ms`;
  els.benchGrid.innerHTML = BENCHMARK_CARDS.map((card) => `
    <article class="bench-card">
      <div class="bench-label">
        ${iconMarkup(card.icon)}
        <span>${escapeHtml(card.label)}</span>
      </div>
      <div class="metric-value">${escapeHtml(card.formatter(benchmark[card.key]))}</div>
    </article>
  `).join("");
}

function renderAll() {
  renderStatus();
  renderCollectionSpectrum();
  renderCollectionList();
  renderTrendChart();
  renderActivityFeed();
  renderSummaryMetrics();
  renderUploads();
  renderProcessedUploads();
  renderProcessSummary();
  renderQualityReport();
  renderSearchResults();
  renderBenchmark();
}

async function refreshHealth() {
  try {
    const payload = await requestJson("/api/health", {}, 15000);
    state.online = payload.status === "ok";
    state.version = payload.version || "";
  } catch (error) {
    state.online = false;
    state.version = "";
  }
  renderStatus();
}

async function refreshStats() {
  const stats = await requestJson("/api/stats");
  state.stats = stats;
  state.primaryCollection = choosePrimaryCollection(stats.collections);
  state.primaryStats = state.primaryCollection
    ? await requestJson(`/api/stats?collection=${encodeURIComponent(state.primaryCollection)}`)
    : null;
  rememberTimeline("stats");
  renderCollectionSpectrum();
  renderCollectionList();
  renderTrendChart();
  renderSummaryMetrics();
}

async function refreshUploads() {
  const payload = await requestJson("/api/uploads");
  state.uploads = Array.isArray(payload.files) ? payload.files : [];
  state.pendingUploads = Array.isArray(payload.pending) ? payload.pending : state.uploads.filter((item) => item.status !== "processed");
  state.processedUploads = Array.isArray(payload.processed) ? payload.processed : state.uploads.filter((item) => item.status === "processed");
  syncUploadSelections();
  renderUploads();
  renderProcessedUploads();
}

async function refreshAll() {
  setStatusLevel("warning");
  if (els.refreshStamp) els.refreshStamp.textContent = "正在同步...";
  try {
    await refreshHealth();
    if (!state.online) {
      renderAll();
      return;
    }
    await Promise.all([refreshStats(), refreshUploads()]);
    renderAll();
  } catch (error) {
    addActivity("danger", "同步失败", error.message || String(error));
    showToast(error.message || "同步失败", "danger");
  } finally {
    renderStatus();
  }
}

function isSupportedFile(file) {
  const name = String(file?.name || "");
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  return SUPPORTED_EXTENSIONS.has(ext);
}

async function uploadFiles(fileList) {
  const files = Array.from(fileList || []).filter(isSupportedFile);
  if (!files.length) {
    showToast("没有可上传的受支持文件。", "warning");
    return;
  }

  addActivity("warning", "开始上传", `待上传 ${files.length} 个文件`);
  let successCount = 0;
  let failedCount = 0;

  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    if (els.uploadQueueMeta) {
      els.uploadQueueMeta.textContent = `正在上传 ${index + 1}/${files.length}: ${file.name}`;
    }

    const form = new FormData();
    form.append("file", file, file.name);
    form.append("relative_path", file.webkitRelativePath || file.name);

    try {
      await requestJson("/api/upload", {
        method: "POST",
        body: form
      }, 120000);
      successCount += 1;
    } catch (error) {
      failedCount += 1;
      addActivity("danger", "上传失败", `${file.name}: ${error.message || error}`);
    }
  }

  await refreshUploads();
  const message = `上传完成，成功 ${successCount} 个，失败 ${failedCount} 个`;
  addActivity(failedCount ? "warning" : "success", "上传完成", message);
  showToast(message, failedCount ? "warning" : "success");
}

async function deleteUpload(filename, options = {}) {
  const purgeVectors = Boolean(options.purgeVectors);
  const suffix = purgeVectors ? "?purge_vectors=true" : "";
  await requestJson(`/api/uploads/${encodeURIComponent(filename)}${suffix}`, { method: "DELETE" });
  addActivity("success", purgeVectors ? "已删除处理文件" : "已移出上传目录", splitUploadPath(uploadDisplayName(filename)).file);
  if (purgeVectors) {
    await Promise.all([refreshUploads(), refreshStats()]);
  } else {
    await refreshUploads();
  }
  showToast(purgeVectors ? `已删除 ${splitUploadPath(uploadDisplayName(filename)).file} 并清理向量` : `已移除 ${splitUploadPath(uploadDisplayName(filename)).file}`, "success");
}

async function deleteProcessedUploads(filenames) {
  const selected = Array.from(new Set((filenames || []).filter(Boolean)));
  if (!selected.length) {
    showToast("请先勾选要删除的已处理文件。", "warning");
    return;
  }
  if (!window.confirm(`确认删除 ${selected.length} 个已处理文件，并同步清理对应向量吗？`)) return;

  const result = await requestJson("/api/uploads/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filenames: selected, purge_vectors: true })
  }, 120000);

  addActivity("success", "已删除处理文件", `删除 ${selected.length} 个文件，清理 ${formatNumber(result.chunks_deleted || 0)} 个片段`);
  state.selectedProcessedUploads.clear();
  state.processedEditMode = false;
  await Promise.all([refreshUploads(), refreshStats()]);
  renderProcessSummary();
  renderQualityReport();
  renderSummaryMetrics();
  showToast(`已删除 ${selected.length} 个文件，并同步清理向量数据。`, "success");
}

function toggleProcessedEditMode(force) {
  state.processedEditMode = typeof force === "boolean" ? force : !state.processedEditMode;
  if (!state.processedEditMode) state.selectedProcessedUploads.clear();
  renderProcessedUploads();
}

async function runProcess() {
  const selected = getPendingUploads()
    .filter((item) => state.selectedUploads.has(item.filename))
    .map((item) => item.filename);

  if (!selected.length) {
    showToast("请先在上传目录里勾选要处理的文件。", "warning");
    return;
  }

  if (els.btnProcess) {
    els.btnProcess.disabled = true;
    els.btnProcess.dataset.busy = "true";
  }
  if (els.processFill) els.processFill.style.width = "18%";
  if (els.processLog) renderEmpty(els.processLog, "正在处理选中的文件，请稍候...");

  try {
    addActivity("warning", "开始入库处理", `本次处理 ${selected.length} 个勾选文件`);
    const result = await requestJson("/api/process", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        filenames: selected,
        collection: state.primaryCollection || "power_equipment"
      })
    }, 300000);

    state.lastProcess = result;
    if (els.processFill) els.processFill.style.width = "100%";

    addActivity(
      result.files_failed ? "warning" : "success",
      "处理完成",
      `成功 ${result.files_succeeded || 0} 个文件，写入 ${result.chunks_written || 0} 个片段`
    );

    await Promise.all([refreshStats(), refreshUploads()]);
    renderProcessSummary();
    renderQualityReport();
    renderSummaryMetrics();
    showToast(`处理完成，成功 ${result.files_succeeded || 0} 个，跳过 ${((result.skipped_already_processed || []).length || 0)} 个已处理文件。`, "success");
  } catch (error) {
    if (els.processFill) els.processFill.style.width = "0%";
    addActivity("danger", "处理失败", error.message || String(error));
    renderProcessSummary();
    showToast(error.message || "处理失败", "danger");
  } finally {
    if (els.btnProcess) {
      delete els.btnProcess.dataset.busy;
      els.btnProcess.disabled = false;
    }
    renderUploads();
  }
}

async function runSearch() {
  const query = String(els.searchInput?.value || "").trim();
  if (!query) {
    showToast("请输入检索问题。", "warning");
    return;
  }

  if (els.searchMeta) els.searchMeta.textContent = "正在检索...";
  try {
    const params = new URLSearchParams({
      q: query,
      top_k: String(Number(els.searchTopK?.value || 5))
    });
    if (state.primaryCollection) params.set("collection", state.primaryCollection);

    const result = await requestJson(`/api/search?${params.toString()}`);
    state.lastSearch = result;
    rememberTimeline("search");
    renderSearchResults();
    renderTrendChart();
    renderSummaryMetrics();
    addActivity(
      result.results?.length ? "success" : "warning",
      "检索完成",
      `查询“${query}”返回 ${result.results?.length || 0} 条结果`
    );
    showToast(`检索完成，返回 ${result.results?.length || 0} 条结果。`, "success");
  } catch (error) {
    addActivity("danger", "检索失败", error.message || String(error));
    state.lastSearch = {
      query,
      results: [],
      message: error.message || "检索失败"
    };
    renderSearchResults();
    showToast(error.message || "检索失败", "danger");
  }
}

async function deleteCollection(name) {
  await requestJson(`/api/collections/${encodeURIComponent(name)}`, { method: "DELETE" });
  if (state.primaryCollection === name) {
    state.primaryCollection = "";
    state.primaryStats = null;
  }
  addActivity("success", "集合已删除", name);
  await refreshStats();
  showToast(`已删除集合 ${name}`, "success");
}

async function runBenchmark() {
  const payload = {
    collection: `benchmark_${Date.now()}`,
    document_count: Number(els.benchDocs?.value || 500),
    batch_size: Number(els.benchBatch?.value || 100),
    query_count: Number(els.benchQueries?.value || 50),
    top_k: Number(els.benchTopK?.value || 5),
    backend: "hashing",
    cleanup: true
  };

  if (els.btnBench) els.btnBench.disabled = true;
  if (els.benchFill) els.benchFill.style.width = "18%";
  if (els.benchLog) els.benchLog.textContent = "压测运行中...";

  try {
    addActivity("warning", "开始压测", `${payload.document_count} 文档 / ${payload.query_count} 查询`);
    const result = await requestJson("/api/benchmark", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }, 300000);

    state.benchmark = result;
    if (els.benchFill) els.benchFill.style.width = "100%";
    rememberTimeline("benchmark");
    renderBenchmark();
    renderTrendChart();
    renderSummaryMetrics();
    addActivity("success", "压测完成", `写入 ${result.insert_docs_per_second} docs/s，检索 ${result.query_qps} qps`);
    showToast("压测完成，指标已更新。", "success");
  } catch (error) {
    if (els.benchFill) els.benchFill.style.width = "0%";
    addActivity("danger", "压测失败", error.message || String(error));
    showToast(error.message || "压测失败", "danger");
  } finally {
    if (els.btnBench) els.btnBench.disabled = false;
  }
}

function activateGroupButton(group, matcher) {
  group?.querySelectorAll(".segment-btn").forEach((button) => {
    button.classList.toggle("active", matcher(button));
  });
}

function handleGlobalCommand(event) {
  event.preventDefault();
  const query = String(els.globalSearchInput?.value || "").trim();
  if (!query) return;

  if (/上传|数据|队列|文件/.test(query)) {
    setPage("data");
    return;
  }
  if (/架构|流程|结构/.test(query)) {
    setPage("architecture");
    return;
  }
  if (/压测|性能|benchmark/.test(query)) {
    setPage("benchmark");
    return;
  }
  if (/概览|总览|统计/.test(query)) {
    setPage("overview");
    return;
  }

  setPage("search");
  if (els.searchInput) els.searchInput.value = query;
  runSearch();
}

function bindEvents() {
  els.sidebarToggle?.addEventListener("click", () => {
    els.sidebar?.classList.toggle("is-collapsed");
    syncSidebarToggleIcon();
  });

  els.navList?.addEventListener("click", (event) => {
    const button = event.target.closest(".nav-item");
    if (!button) return;
    setPage(button.dataset.page);
  });

  document.querySelectorAll("[data-jump]").forEach((button) => {
    button.addEventListener("click", () => setPage(button.dataset.jump));
  });

  els.refreshBtn?.addEventListener("click", refreshAll);
  els.globalSearchForm?.addEventListener("submit", handleGlobalCommand);

  els.pickFilesButton?.addEventListener("click", () => els.fileInput?.click());
  els.pickFolderButton?.addEventListener("click", () => els.folderInput?.click());
  els.dropFolderButton?.addEventListener("click", () => els.folderInput?.click());
  els.dropBrowseButton?.addEventListener("click", () => els.queueList?.scrollIntoView({ behavior: "smooth", block: "start" }));
  els.reloadQueueButton?.addEventListener("click", refreshUploads);
  els.selectAllUploads?.addEventListener("click", () => {
    state.selectedUploads = new Set(getPendingUploads().map((item) => item.filename));
    renderUploads();
  });
  els.clearUploadSelection?.addEventListener("click", () => {
    state.selectedUploads.clear();
    renderUploads();
  });
  els.processedEditButton?.addEventListener("click", () => toggleProcessedEditMode());
  els.processedDeleteButton?.addEventListener("click", async () => {
    await deleteProcessedUploads(Array.from(state.selectedProcessedUploads));
  });

  els.fileInput?.addEventListener("change", async (event) => {
    await uploadFiles(event.target.files);
    event.target.value = "";
  });

  els.folderInput?.addEventListener("change", async (event) => {
    await uploadFiles(event.target.files);
    event.target.value = "";
  });

  els.dropZone?.addEventListener("dragover", (event) => {
    event.preventDefault();
    els.dropZone.classList.add("is-dragging");
  });

  els.dropZone?.addEventListener("dragleave", () => {
    els.dropZone.classList.remove("is-dragging");
  });

  els.dropZone?.addEventListener("drop", async (event) => {
    event.preventDefault();
    els.dropZone.classList.remove("is-dragging");
    await uploadFiles(event.dataTransfer?.files);
  });

  els.btnProcess?.addEventListener("click", runProcess);

  els.searchInput?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      runSearch();
    }
  });
  els.btnSearch?.addEventListener("click", runSearch);

  els.btnBench?.addEventListener("click", runBenchmark);

  els.collList?.addEventListener("click", async (event) => {
    const selectButton = event.target.closest("[data-set-collection]");
    const deleteButton = event.target.closest("[data-delete-collection]");

    if (selectButton) {
      state.primaryCollection = selectButton.dataset.setCollection;
      state.primaryStats = await requestJson(`/api/stats?collection=${encodeURIComponent(state.primaryCollection)}`);
      renderCollectionList();
      renderSummaryMetrics();
      showToast(`默认集合已切换为 ${state.primaryCollection}`, "success");
      return;
    }

    if (deleteButton) {
      const name = deleteButton.dataset.deleteCollection;
      if (!window.confirm(`确认删除集合 ${name} 吗？`)) return;
      await deleteCollection(name);
    }
  });

  els.queueList?.addEventListener("change", (event) => {
    const input = event.target.closest("[data-upload-select]");
    if (!input) return;
    const name = input.dataset.uploadSelect;
    if (input.checked) state.selectedUploads.add(name);
    else state.selectedUploads.delete(name);
    renderUploads();
  });

  els.queueList?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-delete-upload]");
    if (!button) return;
    await deleteUpload(button.dataset.deleteUpload);
  });

  els.processedList?.addEventListener("change", (event) => {
    const input = event.target.closest("[data-processed-select]");
    if (!input) return;
    const name = input.dataset.processedSelect;
    if (input.checked) state.selectedProcessedUploads.add(name);
    else state.selectedProcessedUploads.delete(name);
    renderProcessedUploads();
  });

  els.searchResults?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-result-toggle]");
    if (!button) return;
    const key = button.dataset.resultToggle;
    if (state.expandedResults.has(key)) state.expandedResults.delete(key);
    else state.expandedResults.add(key);
    renderSearchResults();
  });

  els.trendModeGroup?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-trend-mode]");
    if (!button) return;
    state.trendMode = button.dataset.trendMode;
    activateGroupButton(els.trendModeGroup, (item) => item.dataset.trendMode === state.trendMode);
    renderTrendChart();
  });

  els.activityFilterGroup?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-activity-filter]");
    if (!button) return;
    state.activityFilter = button.dataset.activityFilter;
    activateGroupButton(els.activityFilterGroup, (item) => item.dataset.activityFilter === state.activityFilter);
    renderActivityFeed();
  });
}

async function init() {
  resolveEls();
  syncSidebarToggleIcon();
  bindEvents();
  setPage("overview");
  addActivity("warning", "前端已加载", "正在连接后端服务并同步 Chroma 统计。");
  renderAll();
  await refreshAll();
}

window.addEventListener("DOMContentLoaded", init);
