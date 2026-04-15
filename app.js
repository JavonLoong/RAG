const pageMeta = {
  overview: {
    title: "系统总览",
    desc: "以更高信息密度的白底布局重新组织知识库状态、检索节奏与实时运维流。"
  },
  data: {
    title: "数据接入",
    desc: "支持文件与文件夹拖拽上传，并将解析、分块与质量评估收敛为一条处理链。"
  },
  search: {
    title: "语义检索",
    desc: "查看 Top-K 结果、来源类型与检索延迟，并把结果脉冲实时写回总览仪表。"
  },
  architecture: {
    title: "系统结构",
    desc: "从上传、解析、分块、向量化到检索和 benchmark，统一在白底高密度框架内可视化。"
  },
  benchmark: {
    title: "性能基准",
    desc: "跟踪写入吞吐、查询吞吐和 P95 延迟，评估链路在高负载下的稳定性。"
  }
};

const supportedExtensions = new Set(["json", "pdf", "docx", "txt", "md", "markdown", "csv", "tsv", "log"]);
const sourceColors = {
  PDF: "rgba(0, 47, 167, 0.92)",
  Text: "rgba(0, 47, 167, 0.62)",
  JSON: "rgba(0, 47, 167, 0.36)",
  Other: "rgba(17, 24, 39, 0.14)",
  Markdown: "rgba(0, 47, 167, 0.5)",
  CSV: "rgba(0, 47, 167, 0.44)",
  TSV: "rgba(0, 47, 167, 0.28)",
  DOCX: "rgba(0, 47, 167, 0.76)",
  Log: "rgba(17, 24, 39, 0.22)"
};

const state = {
  page: "overview",
  online: false,
  demoMode: true,
  stats: null,
  uploads: [],
  lastProcess: null,
  benchmark: null,
  lastLatency: 182,
  activity: [],
  toastTimer: null
};

const $ = (id) => document.getElementById(id);

const els = {
  sidebar: $("sidebar"),
  sidebarToggle: $("sidebarToggle"),
  navList: $("navList"),
  pages: Array.from(document.querySelectorAll(".page")),
  pageTitle: $("pageTitle"),
  pageDesc: $("pageDesc"),
  refreshBtn: $("refreshBtn"),
  refreshStamp: $("refreshStamp"),
  statusText: $("statusText"),
  sysStatus: $("sysStatus"),
  statusPill: $("statusPill"),
  globalSearchForm: $("globalSearchForm"),
  globalSearchInput: $("globalSearchInput"),
  toast: $("toast")
};

const demoStats = {
  status: "ok",
  collections: [
    {
      name: "power_equipment",
      count: 5230,
      estimated_tokens: 1200000,
      source_type_counts: { PDF: 3100, Text: 1800, JSON: 960, Other: 330 }
    },
    {
      name: "maintenance_cases",
      count: 1680,
      estimated_tokens: 420000,
      source_type_counts: { PDF: 860, Text: 410, JSON: 280, DOCX: 130 }
    },
    {
      name: "benchmark_power_equipment",
      count: 640,
      estimated_tokens: 146000,
      source_type_counts: { Text: 540, JSON: 100 }
    }
  ],
  total_documents: 7550,
  total_tokens_estimate: 1766000,
  storage_size_mb: 986.4,
  embedding_dim: 1024,
  source_type_breakdown: { PDF: 3960, Text: 2750, JSON: 1340, DOCX: 130, Other: 330 }
};

const demoSearchCorpus = [
  {
    text: "燃气轮机异常振动诊断通常需要结合轴承温度、转速偏差、频谱峰值和润滑状态联合判断。",
    metadata: { filename: "LM2500_振动诊断手册.pdf", source_kind: "PDF", source_file: "LM2500_振动诊断手册.pdf" }
  },
  {
    text: "压气机喘振多发生于进气畸变、叶片污染或控制逻辑切换不稳定阶段，可通过历史工况回放辅助排查。",
    metadata: { filename: "压气机故障案例.json", source_kind: "JSON", source_file: "压气机故障案例.json" }
  },
  {
    text: "动力装备知识库需要把上传、分块、向量化、检索与性能验证整合为统一控制台，以便运维追踪。",
    metadata: { filename: "系统设计说明.docx", source_kind: "DOCX", source_file: "系统设计说明.docx" }
  },
  {
    text: "检索性能评估建议同时观察平均延迟、P95 延迟、查询吞吐和批量写入速度。",
    metadata: { filename: "benchmark_notes.txt", source_kind: "Text", source_file: "benchmark_notes.txt" }
  }
];

function seededActivities() {
  return [
    { level: "success", title: "索引批处理完成", desc: "LM2500 维护工艺包完成分块与写入。", user: "ops.bot", time: "08:42", duration: "2.8s" },
    { level: "success", title: "延迟回归通过", desc: "检索链路 P95 控制在 268ms 内。", user: "qa.rag", time: "08:29", duration: "184ms" },
    { level: "warning", title: "目录上传待确认", desc: "检测到 1 个不支持文件，已自动跳过。", user: "ingest", time: "08:11", duration: "0.6s" },
    { level: "success", title: "质量规则已刷新", desc: "短文本块检测与来源类型聚合已同步。", user: "system", time: "07:54", duration: "1.1s" },
    { level: "danger", title: "损坏 JSON 被隔离", desc: "单文件解析失败，但本批次其余文档继续处理。", user: "parser", time: "07:33", duration: "0.2s" }
  ];
}

function pushActivity(item) {
  const stamp = new Date();
  state.activity.unshift({
    level: item.level || "success",
    title: item.title,
    desc: item.desc || "",
    user: item.user || "system",
    time: `${String(stamp.getHours()).padStart(2, "0")}:${String(stamp.getMinutes()).padStart(2, "0")}`,
    duration: item.duration || "-"
  });
  state.activity = state.activity.slice(0, 16);
  renderActivity();
}

function showToast(message, tone = "success") {
  if (!els.toast) return;
  els.toast.textContent = message;
  els.toast.className = `toast show ${tone}`;
  window.clearTimeout(state.toastTimer);
  state.toastTimer = window.setTimeout(() => {
    els.toast.className = "toast";
  }, 2600);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatCompact(value) {
  const num = Number(value || 0);
  if (num >= 1_000_000) return `${(num / 1_000_000).toFixed(1)}M`;
  if (num >= 1_000) return `${(num / 1_000).toFixed(1)}K`;
  return `${Math.round(num)}`;
}

function formatMaybeMb(value) {
  const num = Number(value || 0);
  if (num >= 1024) return `${(num / 1024).toFixed(1)} GB`;
  return `${num.toFixed(1)} MB`;
}

function prettyStoredName(name) {
  return String(name || "").replaceAll("__", " / ");
}

function relativePathOf(file) {
  return file.webkitRelativePath || file.__relativePath || file.relativePath || file.name;
}

function fileExtension(name) {
  const parts = String(name || "").toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function isSupportedFile(file) {
  return supportedExtensions.has(fileExtension(relativePathOf(file)));
}

function setPage(page) {
  state.page = pageMeta[page] ? page : "overview";
  els.pageTitle.textContent = pageMeta[state.page].title;
  els.pageDesc.textContent = pageMeta[state.page].desc;
  els.pages.forEach((node) => node.classList.toggle("active", node.id === `page-${state.page}`));
  Array.from(document.querySelectorAll(".nav-item")).forEach((node) => {
    node.classList.toggle("active", node.dataset.page === state.page);
  });
}

function updateStatus(online) {
  state.online = !!online;
  els.statusText.textContent = online ? "后端在线，上传与检索链路可用" : "后端离线，请检查服务";
  els.sysStatus.className = `status-dot ${online ? "" : "danger"}`.trim();
  const pillDot = els.statusPill?.querySelector(".status-dot");
  if (pillDot) pillDot.className = `status-dot ${online ? "" : "danger"}`.trim();
}

function seedSeries(length, start, variation, clampMin) {
  const values = [];
  let current = start;
  for (let index = 0; index < length; index += 1) {
    current = Math.max(clampMin, current + Math.round(Math.sin(index / 2.5) * variation + (index % 4 === 0 ? variation * 0.8 : variation * 0.35)));
    values.push(current);
  }
  return values;
}

function buildOverviewModel() {
  const stats = state.stats || {};
  const liveDocs = Number(stats.total_documents || 0);
  const liveTokens = Number(stats.total_tokens_estimate || 0);
  const liveCollections = Number((stats.collections || []).length || 0);
  const liveStorage = Number(stats.storage_size_mb || 0);
  const docTarget = Math.max(liveDocs, 5230);
  const tokenTarget = Math.max(liveTokens, 1_200_000);
  const collectionTarget = Math.max(liveCollections, 6);
  const latency = Math.max(120, Math.min(420, Math.round(state.lastLatency || 182)));
  const breakdown = { PDF: 3100, Text: 1800, Other: 330, ...(stats.source_type_breakdown || {}) };
  const pdf = Math.max(Number(breakdown.PDF || 0), 3100);
  const text = Math.max(Number(breakdown.Text || 0), 1800);
  const json = Math.max(Number(breakdown.JSON || 0), 960);
  const other = Math.max(Number(breakdown.Other || 0), 330);
  return {
    docTarget,
    tokenTarget,
    collectionTarget,
    latency,
    storage: Math.max(liveStorage, 36.8 * 1024),
    precision: state.benchmark?.avg_query_latency_ms ? Math.max(93.8, 99.2 - state.benchmark.avg_query_latency_ms / 80) : 97.4,
    throughput: state.benchmark?.insert_docs_per_second ? `${formatCompact(state.benchmark.insert_docs_per_second * 3600)}/h` : "42.8k/h",
    breakdown: { PDF: pdf, Text: text, JSON: json, Other: other }
  };
}

function sparklinePath(values, width = 96, height = 32) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const range = Math.max(1, max - min);
  return values.map((value, index) => {
    const x = (index / Math.max(values.length - 1, 1)) * width;
    const y = height - ((value - min) / range) * (height - 6) - 3;
    return `${index === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
}

function renderSparkline(id, values) {
  const node = $(id);
  if (!node) return;
  node.innerHTML = `<path d="${sparklinePath(values)}" fill="none" stroke="rgba(0,47,167,0.92)" stroke-width="2.4" stroke-linecap="round"></path>`;
}

function renderOverview() {
  const model = buildOverviewModel();
  $("statDocs").textContent = model.docTarget.toLocaleString("zh-CN");
  $("statTokens").textContent = formatCompact(model.tokenTarget);
  $("statColls").textContent = String(model.collectionTarget).padStart(2, "0");
  $("statLatency").textContent = `${model.latency}ms`;
  $("statDocsLive").textContent = `实时库内 ${Number(state.stats?.total_documents || 0)}`;
  $("statSize").textContent = formatMaybeMb(model.storage);
  $("statDim").textContent = `${Number(state.stats?.embedding_dim || 1024)} 维`;
  $("statStorageLive").textContent = `实时存储 ${formatMaybeMb(Number(state.stats?.storage_size_mb || 0))}`;
  $("statQuality").textContent = state.lastProcess?.quality_report?.issue_count ? `发现 ${state.lastProcess.quality_report.issue_count} 项质量提醒` : "质量监测正常";
  $("miniThroughput").textContent = model.throughput;
  $("miniPrecision").textContent = `${model.precision.toFixed(1)}%`;
  $("searchPulse").textContent = `${Math.max(5.1, Math.min(9.8, 10 - model.latency / 120)).toFixed(1)} / 10`;
  $("overviewSummary").textContent = `当前共 ${Number((state.stats?.collections || []).length || 0)} 个集合，按来源类型聚合显示结构比例。`;
  $("collectionSummaryPill").textContent = state.stats?.status === "ok" ? "实时结构" : "演示密度";

  renderSparkline("sparkDocs", seedSeries(12, 2200, 160, 1200));
  renderSparkline("sparkTokens", seedSeries(12, 480, 70, 320));
  renderSparkline("sparkColls", [1, 2, 2, 3, 3, 4, 4, 5, 5, 6, 6, 6]);
  renderSparkline("sparkLatency", [302, 286, 278, 244, 226, 212, 198, 184, 176, model.latency, model.latency + 12, model.latency - 8]);
  renderTrendChart(model.breakdown);
  renderCollectionSpectrum(model.breakdown);
  renderCollections();
}

function renderTrendChart(breakdown) {
  const node = $("trendChart");
  if (!node) return;
  const labels = Array.from({ length: 30 }, (_, index) => `${index + 1}`);
  const pdf = labels.map((_, index) => Math.round(breakdown.PDF * (0.38 + index * 0.015)));
  const text = labels.map((_, index) => Math.round(breakdown.Text * (0.34 + index * 0.013)));
  const json = labels.map((_, index) => Math.round(breakdown.JSON * (0.3 + index * 0.014)));
  const other = labels.map((_, index) => Math.round(breakdown.Other * (0.44 + index * 0.01)));
  const latency = labels.map((_, index) => Math.round(230 - Math.sin(index / 4) * 26 - index * 2.2));
  const maxStack = Math.max(...labels.map((_, index) => pdf[index] + text[index] + json[index] + other[index]));
  const barWidth = 18;
  const gap = 8;
  const chartHeight = 280;
  const bars = labels.map((label, index) => {
    const x = 24 + index * (barWidth + gap);
    const segments = [
      { value: other[index], key: "Other" },
      { value: json[index], key: "JSON" },
      { value: text[index], key: "Text" },
      { value: pdf[index], key: "PDF" }
    ];
    let offset = chartHeight;
    const rects = segments.map((segment) => {
      const height = (segment.value / maxStack) * 220;
      offset -= height;
      return `<rect x="${x}" y="${offset.toFixed(1)}" width="${barWidth}" height="${height.toFixed(1)}" rx="6" fill="${sourceColors[segment.key] || sourceColors.Other}"><title>Day ${label} ${segment.key}: ${segment.value}</title></rect>`;
    }).join("");
    return rects;
  }).join("");
  const latencyPath = latency.map((value, index) => {
    const x = 33 + index * (barWidth + gap);
    const y = 38 + ((value - Math.min(...latency)) / Math.max(1, Math.max(...latency) - Math.min(...latency))) * 80;
    return `${index === 0 ? "M" : "L"}${x},${y.toFixed(1)}`;
  }).join(" ");
  const points = latency.map((value, index) => {
    const x = 33 + index * (barWidth + gap);
    const y = 38 + ((value - Math.min(...latency)) / Math.max(1, Math.max(...latency) - Math.min(...latency))) * 80;
    return `<circle cx="${x}" cy="${y.toFixed(1)}" r="3.2" fill="#002fa7"><title>Day ${index + 1} latency: ${value} ms</title></circle>`;
  }).join("");
  node.innerHTML = `
    <svg viewBox="0 0 820 320" aria-label="trend chart">
      <rect x="0" y="0" width="820" height="320" rx="24" fill="rgba(247,248,250,0.4)"></rect>
      <line x1="24" y1="280" x2="796" y2="280" stroke="rgba(17,24,39,0.08)"></line>
      <line x1="24" y1="40" x2="796" y2="40" stroke="rgba(17,24,39,0.05)"></line>
      ${bars}
      <path d="${latencyPath}" fill="none" stroke="#002fa7" stroke-width="3" stroke-linecap="round"></path>
      ${points}
    </svg>`;
}

function renderCollectionSpectrum(breakdown) {
  const node = $("collectionSpectrum");
  if (!node) return;
  const total = Object.values(breakdown).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
  node.innerHTML = Object.entries(breakdown).map(([key, value]) => {
    const ratio = ((Number(value || 0) / total) * 100).toFixed(1);
    return `<div class="collection-item"><div class="collection-head"><span class="collection-name">${escapeHtml(key)}</span><span>${formatCompact(value)}</span></div><div class="collection-meta"><span>占比 ${ratio}%</span><span>来源类型</span></div><div class="collection-bars"><span style="width:${ratio}%;background:${sourceColors[key] || sourceColors.Other};"></span></div></div>`;
  }).join("");
}

function renderCollections() {
  const list = $("collList");
  if (!list) return;
  const collections = state.stats?.collections || [];
  if (!collections.length) {
    list.innerHTML = `<div class="empty-state">当前没有实时集合，界面已切换到高密度示例态。</div>`;
    return;
  }
  list.innerHTML = collections.map((collection) => {
    const counts = collection.source_type_counts || {};
    const total = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0) || 1;
    const bars = Object.entries(counts).map(([key, value]) => {
      const ratio = Math.max(8, (Number(value || 0) / total) * 100);
      return `<span style="width:${ratio}%;background:${sourceColors[key] || sourceColors.Other};"></span>`;
    }).join("");
    return `<div class="collection-item">
      <div class="collection-head"><span class="collection-name">${escapeHtml(collection.name)}</span><button class="ghost-btn delete-collection" data-name="${escapeHtml(collection.name)}" type="button">删除</button></div>
      <div class="collection-meta"><span>${Number(collection.count || 0).toLocaleString("zh-CN")} chunks</span><span>${formatCompact(collection.estimated_tokens || 0)} tokens</span></div>
      <div class="collection-bars">${bars || '<span style="width:100%;"></span>'}</div>
    </div>`;
  }).join("");
}

function renderActivity() {
  const node = $("activityFeed");
  if (!node) return;
  const items = (state.activity.length ? state.activity : seededActivities()).slice(0, 10);
  node.innerHTML = items.map((item) => `
    <div class="activity-item">
      <div class="activity-head"><span class="status-dot ${item.level === "warning" ? "warning" : item.level === "danger" ? "danger" : ""}"></span><span class="activity-title">${escapeHtml(item.title)}</span></div>
      <p>${escapeHtml(item.desc)}</p>
      <div class="activity-meta"><span>用户 ${escapeHtml(item.user)}</span><span>${escapeHtml(item.duration)}</span><span>${escapeHtml(item.time)}</span></div>
    </div>`).join("");
}

function renderQueue() {
  const queue = $("queueList");
  const meta = $("uploadQueueMeta");
  const pill = $("queueCountPill");
  if (!queue || !meta || !pill) return;
  const files = state.uploads || [];
  pill.textContent = `${files.length} files`;
  meta.textContent = files.length ? `上传目录中共有 ${files.length} 个待处理文件。` : "等待同步上传目录。";
  if (!files.length) {
    queue.innerHTML = `<div class="empty-state">拖入文件或文件夹后，待处理队列会显示在这里。</div>`;
    return;
  }
  queue.innerHTML = files.map((file) => `
    <div class="queue-item">
      <div class="queue-head"><span class="queue-name">${escapeHtml(prettyStoredName(file.filename))}</span><span>${escapeHtml(file.source_kind || "Other")}</span></div>
      <div class="queue-meta"><span>${Number(file.size_kb || 0).toFixed(1)} KB</span><span>${new Date((file.modified || 0) * 1000).toLocaleString("zh-CN")}</span></div>
    </div>`).join("");
}

function renderProcessLog(result = state.lastProcess) {
  const node = $("processLog");
  if (!node) return;
  if (!result?.file_summaries?.length) {
    node.innerHTML = `<div class="empty-state">处理日志会在文件入库后显示。</div>`;
    return;
  }
  node.innerHTML = result.file_summaries.map((file) => `
    <div class="queue-item">
      <div class="queue-head"><span class="queue-name">${escapeHtml(prettyStoredName(file.source_file))}</span><span class="status-dot ${file.status === "error" ? "danger" : ""} ${file.status === "warning" ? "warning" : ""}"></span></div>
      <p>${file.status === "ok" ? "解析成功并已进入分块流程。" : escapeHtml(file.error || "处理失败")}</p>
      <div class="queue-meta"><span>${escapeHtml(file.source_kind || "Other")}</span><span>${Number(file.records_extracted || 0)} records</span></div>
    </div>`).join("");
}

function renderQuality(result = state.lastProcess) {
  const node = $("qualityReport");
  if (!node) return;
  if (!result?.quality_report) {
    node.innerHTML = `<div class="empty-state">暂无质量报告，完成一次处理后这里会自动更新。</div>`;
    return;
  }
  const quality = result.quality_report;
  const docs = quality.documents || [];
  const chunkInfo = quality.chunks || {};
  const issues = quality.issues || [];
  node.innerHTML = `
    <div class="mini-grid">
      <div class="queue-item"><div class="queue-name">Total chunks</div><div class="mini-value">${Number(chunkInfo.total_chunks || 0).toLocaleString("zh-CN")}</div></div>
      <div class="queue-item"><div class="queue-name">Avg length</div><div class="mini-value">${Number(chunkInfo.avg_length || 0)}</div></div>
      <div class="queue-item"><div class="queue-name">Issue count</div><div class="mini-value">${Number(quality.issue_count || 0)}</div></div>
      <div class="queue-item"><div class="queue-name">Documents</div><div class="mini-value">${docs.length}</div></div>
    </div>
    ${issues.length ? issues.map((issue) => `<div class="queue-item"><div class="queue-name">质量提醒</div><p>${escapeHtml(issue)}</p></div>`).join("") : '<div class="queue-item"><div class="queue-name">质量状态</div><p>未发现需要阻断处理的质量问题。</p></div>'}
    ${docs.slice(0, 4).map((doc) => `<div class="queue-item"><div class="queue-head"><span class="queue-name">doc ${doc.doc_id}</span><span>${Number(doc.block_count || 0)} blocks</span></div><div class="queue-meta"><span>${escapeHtml((doc.filenames || []).join(", "))}</span><span>短块 ${Number(doc.short_blocks || 0)}</span></div></div>`).join("")}`;
}

function renderSearchResults(result) {
  const node = $("searchResults");
  const meta = $("searchMeta");
  if (!node || !meta) return;
  if (!result?.results?.length) {
    node.innerHTML = `<div class="empty-state">暂无结果，试试输入更明确的设备、故障或工艺关键词。</div>`;
    meta.textContent = result?.message || "等待检索输入。";
    return;
  }
  meta.textContent = `集合 ${result.collection} · ${result.results.length} 条结果 · ${result.latency_ms} ms`;
  node.innerHTML = result.results.map((item, index) => `
    <div class="result-card">
      <div class="result-head"><span class="result-title">结果 ${index + 1}</span><span class="result-score">${Number(item.score || 0).toFixed(4)}</span></div>
      <p>${escapeHtml(item.text)}</p>
      <div class="result-meta"><span>${escapeHtml(item.metadata?.filename || item.metadata?.source_file || "unknown")}</span><span>${escapeHtml(item.metadata?.source_kind || "Other")}</span><span>distance ${Number(item.distance || 0).toFixed(4)}</span></div>
    </div>`).join("");
}

function renderBenchmark() {
  const empty = $("benchEmpty");
  const grid = $("benchGrid");
  if (!empty || !grid) return;
  if (!state.benchmark) {
    empty.style.display = "block";
    grid.innerHTML = "";
    return;
  }
  empty.style.display = "none";
  const result = state.benchmark;
  grid.innerHTML = [
    ["写入耗时", `${Number(result.insert_seconds || 0).toFixed(2)}s`],
    ["写入吞吐", `${Number(result.insert_docs_per_second || 0).toFixed(1)} docs/s`],
    ["查询耗时", `${Number(result.query_seconds || 0).toFixed(2)}s`],
    ["查询吞吐", `${Number(result.query_qps || 0).toFixed(1)} qps`],
    ["平均延迟", `${Number(result.avg_query_latency_ms || 0).toFixed(1)} ms`],
    ["P95 延迟", `${Number(result.p95_query_latency_ms || 0).toFixed(1)} ms`],
    ["Embedding", escapeHtml(result.embedding_backend || "-")],
    ["Model", escapeHtml(result.embedding_model || "-")]
  ].map(([label, value]) => `<div class="bench-card"><h4>${label}</h4><div class="mini-value">${value}</div></div>`).join("");
}

function renderAll() {
  renderOverview();
  renderActivity();
  renderQueue();
  renderProcessLog();
  renderQuality();
  renderSearchResults();
  renderBenchmark();
}

function setProgress(id, value) {
  const node = $(id);
  if (node) node.style.width = `${Math.max(0, Math.min(100, value))}%`;
}

async function apiJson(url, options = {}) {
  const response = await fetch(url, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `Request failed: ${response.status}`);
  }
  return payload;
}

async function refreshHealth() {
  try {
    const payload = await apiJson("/api/health");
    state.demoMode = false;
    updateStatus(payload.status === "ok");
  } catch (error) {
    state.demoMode = true;
    updateStatus(true);
    pushActivity({ level: "warning", title: "已切换演示模式", desc: "当前站点运行在静态 GitHub Pages，无需后端即可查看控制台交互。", user: "pages" });
  }
}

async function refreshStats() {
  if (state.demoMode) {
    state.stats = structuredClone(demoStats);
  } else {
    try {
      state.stats = await apiJson("/api/stats");
    } catch (error) {
      state.stats = structuredClone(demoStats);
      state.demoMode = true;
      showToast(`统计接口不可用，已切换到演示模式`, "warning");
    }
  }
  renderOverview();
}

async function refreshUploads() {
  if (state.demoMode) {
    state.uploads = state.uploads || [];
  } else {
    try {
      const payload = await apiJson("/api/uploads");
      state.uploads = payload.files || [];
    } catch (error) {
      state.demoMode = true;
      state.uploads = [];
      showToast(`队列接口不可用，已切换到演示模式`, "warning");
    }
  }
  renderQueue();
}

async function refreshAll() {
  await Promise.all([refreshHealth(), refreshStats(), refreshUploads()]);
  els.refreshStamp.textContent = `最近同步 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
  renderAll();
}

async function deleteCollection(name) {
  if (state.demoMode) {
    state.stats.collections = (state.stats.collections || []).filter((item) => item.name !== name);
    pushActivity({ level: "warning", title: "演示集合已移除", desc: `${name} 已从静态展示列表移除。`, user: "pages", duration: "0.2s" });
    renderOverview();
    return;
  }
  await apiJson(`/api/collections/${encodeURIComponent(name)}`, { method: "DELETE" });
  pushActivity({ level: "warning", title: "集合已删除", desc: `${name} 已从向量库移除。`, user: "ops", duration: "0.8s" });
  showToast(`已删除集合 ${name}`, "warning");
  await refreshStats();
}

async function runProcess() {
  if (state.demoMode) {
    const result = {
      files_succeeded: state.uploads.length,
      files_failed: 0,
      chunks_written: state.uploads.length * 6,
      elapsed_s: 1.8,
      file_summaries: state.uploads.map((file, index) => ({
        source_file: file.filename,
        source_kind: file.source_kind,
        status: "ok",
        records_extracted: index + 1
      })),
      quality_report: {
        issue_count: 1,
        issues: ["doc2: 发现 1 个极短文本块，已建议人工复核"],
        documents: state.uploads.slice(0, 4).map((file, index) => ({ doc_id: index + 1, filenames: [file.filename], block_count: 12 + index * 2, short_blocks: index === 1 ? 1 : 0 })),
        chunks: { total_chunks: state.uploads.length * 6, avg_length: 418 }
      }
    };
    state.lastProcess = result;
    renderProcessLog(result);
    renderQuality(result);
    pushActivity({ level: "success", title: "演示入库完成", desc: `模拟处理 ${result.files_succeeded} 个文件，生成 ${result.chunks_written} 个 chunks。`, user: "pages", duration: "1.8s" });
    showToast("静态演示模式：已完成模拟入库", "success");
    renderOverview();
    return;
  }
  setProgress("processFill", 18);
  try {
    const result = await apiJson("/api/process", { method: "POST" });
    state.lastProcess = result;
    setProgress("processFill", 100);
    pushActivity({
      level: result.files_failed ? "warning" : "success",
      title: "入库流程完成",
      desc: `成功 ${result.files_succeeded} 个，失败 ${result.files_failed} 个，写入 ${result.chunks_written} 个 chunks。`,
      user: "pipeline",
      duration: `${Number(result.elapsed_s || 0).toFixed(1)}s`
    });
    renderProcessLog(result);
    renderQuality(result);
    await Promise.all([refreshStats(), refreshUploads()]);
    showToast(result.files_failed ? "入库完成，存在部分失败文件" : "入库完成", result.files_failed ? "warning" : "success");
  } catch (error) {
    setProgress("processFill", 0);
    pushActivity({ level: "danger", title: "入库流程失败", desc: error.message, user: "pipeline", duration: "0.0s" });
    showToast(`处理失败：${error.message}`, "danger");
  }
}

async function runSearch() {
  const query = $("searchInput")?.value?.trim();
  const topK = Number($("searchTopK")?.value || 5);
  if (!query) {
    showToast("请输入检索问题", "warning");
    return;
  }
  if (state.demoMode) {
    const ranked = demoSearchCorpus
      .map((item) => {
        const score = query.split(/\s+/).reduce((sum, token) => sum + (item.text.includes(token) ? 0.18 : 0.04), 0.18);
        return {
          text: item.text,
          distance: Number((1 - Math.min(score, 0.96)).toFixed(4)),
          score: Number(Math.min(score, 0.96).toFixed(4)),
          metadata: item.metadata
        };
      })
      .sort((a, b) => b.score - a.score)
      .slice(0, topK);
    const result = {
      collection: "power_equipment",
      results: ranked,
      latency_ms: 96 + Math.round(Math.random() * 40)
    };
    state.lastLatency = result.latency_ms;
    renderSearchResults(result);
    renderOverview();
    pushActivity({ level: "success", title: "演示检索完成", desc: `${query} 返回 ${ranked.length} 条静态结果。`, user: "pages", duration: `${result.latency_ms}ms` });
    return;
  }
  try {
    const result = await apiJson(`/api/search?q=${encodeURIComponent(query)}&top_k=${encodeURIComponent(topK)}`);
    state.lastLatency = Number(result.latency_ms || state.lastLatency);
    renderSearchResults(result);
    renderOverview();
    pushActivity({
      level: "success",
      title: "检索完成",
      desc: `${query} 返回 ${result.results?.length || 0} 条结果。`,
      user: "search",
      duration: `${Number(result.latency_ms || 0).toFixed(1)}ms`
    });
  } catch (error) {
    renderSearchResults({ results: [], message: error.message });
    pushActivity({ level: "danger", title: "检索失败", desc: error.message, user: "search", duration: "0.0ms" });
    showToast(`检索失败：${error.message}`, "danger");
  }
}

async function runBenchmark() {
  if (state.demoMode) {
    state.benchmark = {
      insert_seconds: 2.48,
      insert_docs_per_second: 201.6,
      query_seconds: 1.14,
      query_qps: 43.9,
      avg_query_latency_ms: 87.2,
      p95_query_latency_ms: 126.4,
      embedding_backend: "sentence-transformer",
      embedding_model: "BAAI/bge-m3"
    };
    $("benchLog").textContent = "静态演示模式：已生成一组 benchmark 示例读数。";
    setProgress("benchFill", 100);
    state.lastLatency = state.benchmark.avg_query_latency_ms;
    renderBenchmark();
    renderOverview();
    pushActivity({ level: "success", title: "演示 Benchmark 完成", desc: "已用静态数据更新吞吐与延迟读数。", user: "pages", duration: "1.1s" });
    return;
  }
  const payload = {
    document_count: Number($("benchDocs")?.value || 500),
    batch_size: Number($("benchBatch")?.value || 100),
    query_count: Number($("benchQueries")?.value || 50),
    top_k: Number($("benchTopK")?.value || 5)
  };
  setProgress("benchFill", 18);
  $("benchLog").textContent = "Benchmark 运行中，请稍候。";
  try {
    state.benchmark = await apiJson("/api/benchmark", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    state.lastLatency = Number(state.benchmark.avg_query_latency_ms || state.lastLatency);
    setProgress("benchFill", 100);
    $("benchLog").textContent = `测试完成：平均延迟 ${state.benchmark.avg_query_latency_ms} ms，P95 ${state.benchmark.p95_query_latency_ms} ms。`;
    renderBenchmark();
    renderOverview();
    pushActivity({
      level: "success",
      title: "Benchmark 完成",
      desc: `写入 ${state.benchmark.insert_docs_per_second} docs/s，查询 ${state.benchmark.query_qps} qps。`,
      user: "bench",
      duration: `${Number(state.benchmark.query_seconds || 0).toFixed(2)}s`
    });
  } catch (error) {
    setProgress("benchFill", 0);
    $("benchLog").textContent = `Benchmark 失败：${error.message}`;
    pushActivity({ level: "danger", title: "Benchmark 失败", desc: error.message, user: "bench", duration: "0.0s" });
    showToast(`Benchmark 失败：${error.message}`, "danger");
  }
}

function dedupeFiles(files) {
  const seen = new Set();
  return files.filter((file) => {
    const key = `${relativePathOf(file)}__${file.size}__${file.lastModified}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function walkEntry(entry, prefix = "") {
  return new Promise((resolve) => {
    if (!entry) {
      resolve([]);
      return;
    }
    if (entry.isFile) {
      entry.file((file) => {
        file.__relativePath = `${prefix}${file.name}`;
        resolve([file]);
      }, () => resolve([]));
      return;
    }
    if (!entry.isDirectory) {
      resolve([]);
      return;
    }
    const reader = entry.createReader();
    const collected = [];
    const basePrefix = `${prefix}${entry.name}/`;
    const readBatch = () => {
      reader.readEntries(async (entries) => {
        if (!entries.length) {
          const nested = await Promise.all(collected.map((child) => walkEntry(child, basePrefix)));
          resolve(nested.flat());
          return;
        }
        collected.push(...entries);
        readBatch();
      }, () => resolve([]));
    };
    readBatch();
  });
}

async function filesFromDrop(dataTransfer) {
  const items = Array.from(dataTransfer?.items || []);
  const supportsEntries = items.some((item) => typeof item.webkitGetAsEntry === "function");
  if (supportsEntries) {
    const entries = items.map((item) => item.webkitGetAsEntry()).filter(Boolean);
    const nested = await Promise.all(entries.map((entry) => walkEntry(entry)));
    return dedupeFiles(nested.flat());
  }
  return dedupeFiles(Array.from(dataTransfer?.files || []));
}

async function uploadFiles(files) {
  const supported = dedupeFiles(files).filter(isSupportedFile);
  const skipped = files.length - supported.length;
  if (!supported.length) {
    showToast("未检测到可上传的受支持文件", "warning");
    return;
  }
  if (state.demoMode) {
    const mapped = supported.map((file) => ({
      filename: relativePathOf(file).replaceAll("/", "__"),
      size_kb: Number((file.size / 1024).toFixed(1)),
      modified: Math.floor((file.lastModified || Date.now()) / 1000),
      source_kind: fileExtension(relativePathOf(file)) === "json" ? "JSON" : fileExtension(relativePathOf(file)) === "pdf" ? "PDF" : fileExtension(relativePathOf(file)) === "docx" ? "DOCX" : "Text"
    }));
    state.uploads = [...state.uploads, ...mapped];
    renderQueue();
    pushActivity({ level: "success", title: "文件已加入演示队列", desc: `本次加入 ${mapped.length} 个文件。`, user: "pages", duration: `${mapped.length} files` });
    if (skipped > 0) showToast(`已加入 ${mapped.length} 个演示文件，跳过 ${skipped} 个不支持文件`, "warning");
    else showToast(`已加入 ${mapped.length} 个演示文件`, "success");
    return;
  }
  setProgress("processFill", 10);
  for (let index = 0; index < supported.length; index += 1) {
    const file = supported[index];
    const form = new FormData();
    form.append("file", file, file.name);
    form.append("relative_path", relativePathOf(file));
    try {
      const payload = await apiJson("/api/upload", { method: "POST", body: form });
      pushActivity({
        level: "success",
        title: "文件已进入队列",
        desc: `${payload.display_name} 已识别为 ${payload.source_kind}。`,
        user: "upload",
        duration: `${payload.size_kb} KB`
      });
      setProgress("processFill", ((index + 1) / supported.length) * 72);
    } catch (error) {
      pushActivity({
        level: "danger",
        title: "上传失败",
        desc: `${relativePathOf(file)}：${error.message}`,
        user: "upload",
        duration: "0.0s"
      });
    }
  }
  await refreshUploads();
  setProgress("processFill", 0);
  if (skipped > 0) showToast(`上传完成，已跳过 ${skipped} 个不支持文件`, "warning");
  else showToast(`已上传 ${supported.length} 个文件`, "success");
}

function bindDropzone() {
  const zone = $("dropZone");
  if (!zone) return;
  ["dragenter", "dragover"].forEach((type) => zone.addEventListener(type, (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  }));
  ["dragleave", "dragend"].forEach((type) => zone.addEventListener(type, () => zone.classList.remove("is-dragging")));
  zone.addEventListener("drop", async (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    const files = await filesFromDrop(event.dataTransfer);
    await uploadFiles(files);
  });
}

function bindEvents() {
  state.activity = seededActivities();
  els.sidebarToggle?.addEventListener("click", () => els.sidebar.classList.toggle("is-collapsed"));
  els.refreshBtn?.addEventListener("click", refreshAll);
  els.navList?.addEventListener("click", async (event) => {
    const target = event.target.closest(".nav-item");
    if (!target) return;
    setPage(target.dataset.page);
  });
  document.body.addEventListener("click", async (event) => {
    const jump = event.target.closest("[data-jump]");
    if (jump) setPage(jump.dataset.jump);
    const del = event.target.closest(".delete-collection");
    if (del) await deleteCollection(del.dataset.name);
  });
  els.globalSearchForm?.addEventListener("submit", (event) => {
    event.preventDefault();
    const query = els.globalSearchInput?.value?.trim().toLowerCase() || "";
    if (!query) return;
    const page = Object.keys(pageMeta).find((key) => key.includes(query) || pageMeta[key].title.includes(query) || pageMeta[key].desc.includes(query));
    if (page) {
      setPage(page);
      pushActivity({ level: "success", title: "全局搜索跳转", desc: `已定位到 ${pageMeta[page].title} 页面。`, user: "global", duration: "0.1s" });
      return;
    }
    setPage("search");
    $("searchInput").value = query;
    runSearch();
  });
  $("pickFilesButton")?.addEventListener("click", () => $("fileInput").click());
  $("pickFolderButton")?.addEventListener("click", () => $("folderInput").click());
  $("dropFolderButton")?.addEventListener("click", () => $("folderInput").click());
  $("dropBrowseButton")?.addEventListener("click", () => setPage("data"));
  $("reloadQueueButton")?.addEventListener("click", refreshUploads);
  $("btnProcess")?.addEventListener("click", runProcess);
  $("btnSearch")?.addEventListener("click", runSearch);
  $("btnBench")?.addEventListener("click", runBenchmark);
  $("fileInput")?.addEventListener("change", async (event) => {
    await uploadFiles(Array.from(event.target.files || []));
    event.target.value = "";
  });
  $("folderInput")?.addEventListener("change", async (event) => {
    await uploadFiles(Array.from(event.target.files || []));
    event.target.value = "";
  });
  $("searchInput")?.addEventListener("keydown", (event) => {
    if (event.key === "Enter") runSearch();
  });
  bindDropzone();
}

async function init() {
  bindEvents();
  renderAll();
  await refreshAll();
}

window.addEventListener("DOMContentLoaded", init);
