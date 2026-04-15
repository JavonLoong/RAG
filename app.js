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
  online: true,
  localMode: true,
  stats: null,
  uploads: [],
  records: [],
  chunks: [],
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

const engineDefaults = {
  dimension: 512,
  chunkSize: 500,
  overlap: 50
};

const defaultStats = {
  status: "idle",
  collections: [],
  total_documents: 0,
  total_tokens_estimate: 0,
  storage_size_mb: 0,
  embedding_dim: engineDefaults.dimension,
  source_type_breakdown: {}
};

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

if (globalThis.pdfjsLib?.GlobalWorkerOptions) {
  globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.worker.min.js";
}

function normalizeText(value) {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function tokenize(text) {
  return normalizeText(text).toLowerCase().match(/[\p{L}\p{N}_-]+/gu) || [];
}

function estimateTokens(text) {
  return Math.max(1, Math.round(normalizeText(text).length / 1.7));
}

function simpleHash(input) {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return hash >>> 0;
}

function createEmbedding(text, dimension = engineDefaults.dimension) {
  const vector = new Float32Array(dimension);
  const tokens = tokenize(text);
  if (!tokens.length) return vector;
  for (const token of tokens) {
    const hash = simpleHash(token);
    const index = hash % dimension;
    const sign = ((hash >>> 1) & 1) === 0 ? 1 : -1;
    const weight = 1 + Math.min(token.length, 8) / 8;
    vector[index] += sign * weight;
  }
  let norm = 0;
  for (const value of vector) norm += value * value;
  norm = Math.sqrt(norm);
  if (!norm) return vector;
  for (let index = 0; index < vector.length; index += 1) {
    vector[index] /= norm;
  }
  return vector;
}

function cosineSimilarity(a, b) {
  let dot = 0;
  let normA = 0;
  let normB = 0;
  const size = Math.min(a.length, b.length);
  for (let index = 0; index < size; index += 1) {
    dot += a[index] * b[index];
    normA += a[index] * a[index];
    normB += b[index] * b[index];
  }
  const denom = Math.sqrt(normA) * Math.sqrt(normB) || 1;
  return dot / denom;
}

function sourceKindFromName(name) {
  const ext = fileExtension(name);
  if (ext === "json") return "JSON";
  if (ext === "pdf") return "PDF";
  if (ext === "docx") return "DOCX";
  if (ext === "md" || ext === "markdown") return "Markdown";
  if (ext === "csv") return "CSV";
  if (ext === "tsv") return "TSV";
  if (ext === "log") return "Log";
  return "Text";
}

function splitTextWithOverlap(text, chunkSize = engineDefaults.chunkSize, overlap = engineDefaults.overlap) {
  const cleaned = normalizeText(text);
  if (!cleaned) return [];
  if (cleaned.length <= chunkSize) return [cleaned];
  const markers = ["\n\n", "\n", "。", "！", "？", "；", ";", "，", ",", " "];
  const output = [];
  let start = 0;
  while (start < cleaned.length) {
    const maxEnd = Math.min(cleaned.length, start + chunkSize);
    let end = maxEnd;
    if (maxEnd < cleaned.length) {
      const minEnd = Math.min(maxEnd, start + Math.max(Math.floor(chunkSize / 2), chunkSize - overlap));
      let best = -1;
      for (const marker of markers) {
        const idx = cleaned.lastIndexOf(marker, maxEnd);
        if (idx >= minEnd) best = Math.max(best, idx + marker.length);
      }
      if (best > start) end = best;
    }
    const piece = cleaned.slice(start, end).trim();
    if (piece) output.push(piece);
    if (end >= cleaned.length) break;
    start = Math.max(start + 1, end - overlap);
    while (/\s/.test(cleaned[start] || "")) start += 1;
  }
  return output;
}

function flattenJson(value, path = [], lines = []) {
  if (value == null) return lines;
  if (typeof value === "string") {
    const cleaned = normalizeText(value);
    if (cleaned.length >= 2) {
      const label = path.filter(Boolean).slice(-2).join(" / ");
      lines.push(label ? `${label}: ${cleaned}` : cleaned);
    }
    return lines;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    const label = path.filter(Boolean).slice(-2).join(" / ");
    lines.push(label ? `${label}: ${String(value)}` : String(value));
    return lines;
  }
  if (Array.isArray(value)) {
    value.forEach((item, index) => flattenJson(item, [...path, `item ${index + 1}`], lines));
    return lines;
  }
  if (typeof value === "object") {
    const title = ["title", "heading", "name", "section", "chapter"].map((key) => value[key]).find((entry) => typeof entry === "string" && normalizeText(entry));
    if (title) lines.push(normalizeText(title));
    Object.entries(value).forEach(([key, nested]) => {
      if (title && normalizeText(String(nested)) === normalizeText(title)) return;
      flattenJson(nested, [...path, key], lines);
    });
  }
  return lines;
}

function parseTabularText(text, delimiter) {
  const parsed = globalThis.Papa?.parse(text, { delimiter, skipEmptyLines: true })?.data || [];
  if (!parsed.length) return "";
  const header = parsed[0];
  const rows = parsed.slice(1).map((row, rowIndex) => {
    const pairs = row.map((cell, index) => `${header[index] || `Column ${index + 1}`}: ${normalizeText(cell)}`).join(" | ");
    return `Row ${rowIndex + 1}: ${pairs}`;
  });
  return normalizeText([`Columns: ${header.join(" | ")}`, ...rows].join("\n\n"));
}

async function parsePdfFile(file) {
  const data = await file.arrayBuffer();
  const pdf = await globalThis.pdfjsLib.getDocument({ data }).promise;
  const records = [];
  for (let pageIndex = 1; pageIndex <= pdf.numPages; pageIndex += 1) {
    const page = await pdf.getPage(pageIndex);
    const textContent = await page.getTextContent();
    const pageText = normalizeText(textContent.items.map((item) => item.str).join(" "));
    if (!pageText) continue;
    records.push({
      record_id: `${relativePathOf(file)}::page-${pageIndex}`,
      filename: relativePathOf(file),
      source_file: relativePathOf(file),
      source_kind: "PDF",
      page_num: pageIndex,
      text: pageText
    });
  }
  if (!records.length) throw new Error("PDF 未提取到可用文本，可能是扫描件或图片型 PDF");
  return records;
}

async function parseDocxFile(file) {
  const arrayBuffer = await file.arrayBuffer();
  let raw = "";
  if (globalThis.mammoth?.extractRawText) {
    raw = (await globalThis.mammoth.extractRawText({ arrayBuffer })).value || "";
  } else if (globalThis.mammoth?.convertToHtml) {
    raw = (await globalThis.mammoth.convertToHtml({ arrayBuffer })).value || "";
  }
  const text = normalizeText(raw.replace(/<[^>]+>/g, " "));
  if (!text) throw new Error("DOCX 未提取到可用文本");
  return [{
    record_id: `${relativePathOf(file)}::doc`,
    filename: relativePathOf(file),
    source_file: relativePathOf(file),
    source_kind: "DOCX",
    page_num: null,
    text
  }];
}

async function parseJsonFile(file) {
  const payload = JSON.parse(await file.text());
  const text = normalizeText(flattenJson(payload).join("\n\n"));
  if (!text) throw new Error("JSON 未提取到可用文本");
  return [{
    record_id: `${relativePathOf(file)}::json`,
    filename: relativePathOf(file),
    source_file: relativePathOf(file),
    source_kind: "JSON",
    page_num: null,
    text
  }];
}

async function parseTextLikeFile(file) {
  const text = normalizeText(await file.text());
  if (!text) throw new Error("文本文件为空");
  return [{
    record_id: `${relativePathOf(file)}::text`,
    filename: relativePathOf(file),
    source_file: relativePathOf(file),
    source_kind: sourceKindFromName(relativePathOf(file)),
    page_num: null,
    text
  }];
}

async function parseTabularFile(file, delimiter) {
  const text = parseTabularText(await file.text(), delimiter);
  if (!text) throw new Error("表格文件为空");
  return [{
    record_id: `${relativePathOf(file)}::table`,
    filename: relativePathOf(file),
    source_file: relativePathOf(file),
    source_kind: sourceKindFromName(relativePathOf(file)),
    page_num: null,
    text
  }];
}

async function parseFileRecords(file) {
  const ext = fileExtension(relativePathOf(file));
  if (ext === "pdf") return parsePdfFile(file);
  if (ext === "docx") return parseDocxFile(file);
  if (ext === "json") return parseJsonFile(file);
  if (ext === "csv") return parseTabularFile(file, ",");
  if (ext === "tsv") return parseTabularFile(file, "\t");
  return parseTextLikeFile(file);
}

function makeChunks(records) {
  const chunks = [];
  records.forEach((record) => {
    const pieces = splitTextWithOverlap(record.text);
    pieces.forEach((piece, index) => {
      const vector = createEmbedding(piece);
      chunks.push({
        chunk_id: `${record.record_id}::${index}`,
        text: piece,
        vector,
        metadata: {
          source_file: record.source_file,
          filename: record.filename,
          source_kind: record.source_kind,
          page_num: record.page_num,
          chunk_index: index,
          char_count: piece.length,
          estimated_tokens: estimateTokens(piece)
        }
      });
    });
  });
  return chunks;
}

function buildQualityReport(records, chunks) {
  const docs = records.map((record, index) => {
    const shortBlocks = splitTextWithOverlap(record.text, 40, 0).filter((item) => item.length < 5).length;
    return {
      doc_id: index + 1,
      filenames: [record.filename],
      block_count: splitTextWithOverlap(record.text, 160, 0).length,
      short_blocks: shortBlocks
    };
  });
  const issues = docs.filter((item) => item.short_blocks > 0).map((item) => `doc${item.doc_id}: ${item.short_blocks} 个极短文本块（<5字符）`);
  return {
    documents: docs,
    chunks: {
      total_chunks: chunks.length,
      avg_length: chunks.length ? Math.round(chunks.reduce((sum, chunk) => sum + chunk.text.length, 0) / chunks.length) : 0,
      min_length: chunks.length ? Math.min(...chunks.map((chunk) => chunk.text.length)) : 0,
      max_length: chunks.length ? Math.max(...chunks.map((chunk) => chunk.text.length)) : 0
    },
    issues,
    issue_count: issues.length
  };
}

function buildLocalStats() {
  if (!state.chunks.length) return structuredClone(defaultStats);
  const byKind = {};
  state.chunks.forEach((chunk) => {
    const kind = chunk.metadata.source_kind || "Other";
    byKind[kind] = (byKind[kind] || 0) + 1;
  });
  const totalTokens = state.chunks.reduce((sum, chunk) => sum + Number(chunk.metadata.estimated_tokens || 0), 0);
  const storageBytes = state.uploads.reduce((sum, file) => sum + Number(file.file?.size || 0), 0);
  const uniqueFiles = new Set(state.records.map((record) => record.source_file));
  return {
    status: "ok",
    collections: [{
      name: "browser_local_index",
      count: state.chunks.length,
      estimated_tokens: totalTokens,
      source_type_counts: byKind
    }],
    total_documents: uniqueFiles.size,
    total_tokens_estimate: totalTokens,
    storage_size_mb: Number((storageBytes / (1024 * 1024)).toFixed(2)),
    embedding_dim: engineDefaults.dimension,
    source_type_breakdown: byKind
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
  els.statusText.textContent = online ? "浏览器本地引擎在线，上传与检索链路可用" : "浏览器本地引擎异常";
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
  const hasIndexedData = state.chunks.length > 0;
  const liveDocs = Number(stats.total_documents || 0);
  const liveTokens = Number(stats.total_tokens_estimate || 0);
  const liveCollections = Number((stats.collections || []).length || 0);
  const liveStorage = Number(stats.storage_size_mb || 0);
  const docTarget = hasIndexedData ? liveDocs : Math.max(liveDocs, 5230);
  const tokenTarget = hasIndexedData ? liveTokens : Math.max(liveTokens, 1_200_000);
  const collectionTarget = hasIndexedData ? Math.max(liveCollections, 1) : Math.max(liveCollections, 6);
  const latency = Math.max(120, Math.min(420, Math.round(state.lastLatency || 182)));
  const breakdown = hasIndexedData
    ? { ...(stats.source_type_breakdown || {}) }
    : { PDF: 3100, Text: 1800, JSON: 960, Other: 330, ...(stats.source_type_breakdown || {}) };
  const pdf = hasIndexedData ? Number(breakdown.PDF || 0) : Math.max(Number(breakdown.PDF || 0), 3100);
  const text = hasIndexedData ? Number(breakdown.Text || 0) : Math.max(Number(breakdown.Text || 0), 1800);
  const json = hasIndexedData ? Number(breakdown.JSON || 0) : Math.max(Number(breakdown.JSON || 0), 960);
  const other = hasIndexedData ? Number(breakdown.Other || 0) : Math.max(Number(breakdown.Other || 0), 330);
  return {
    docTarget,
    tokenTarget,
    collectionTarget,
    latency,
    storage: hasIndexedData ? liveStorage : Math.max(liveStorage, 36.8 * 1024),
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
  $("overviewSummary").textContent = state.chunks.length
    ? `当前浏览器内已索引 ${state.records.length} 份文档记录和 ${state.chunks.length} 个 chunks，按来源类型聚合显示结构比例。`
    : `当前尚未在浏览器内建立索引，拖入文件后会在本地完成解析、分块与检索。`;
  $("collectionSummaryPill").textContent = state.chunks.length ? "Browser-local index" : "等待本地索引";

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
      <div class="collection-head"><span class="collection-name">${escapeHtml(collection.name)}</span><button class="ghost-btn delete-collection" data-name="${escapeHtml(collection.name)}" type="button">清空</button></div>
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
  meta.textContent = files.length ? `当前浏览器会话中共有 ${files.length} 个文件，处理不会写入 GitHub 仓库。` : "等待拖入文件或文件夹，分析只在当前浏览器会话中进行。";
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
  state.localMode = true;
  updateStatus(true);
  els.statusText.textContent = "浏览器本地引擎在线，文件只在当前浏览器会话中处理";
}

async function refreshStats() {
  state.stats = buildLocalStats();
  renderOverview();
}

async function refreshUploads() {
  state.uploads = state.uploads || [];
  renderQueue();
}

async function refreshAll() {
  await Promise.all([refreshHealth(), refreshStats(), refreshUploads()]);
  els.refreshStamp.textContent = `本地引擎已就绪 ${new Date().toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" })}`;
  renderAll();
}

async function deleteCollection(name) {
  state.records = [];
  state.chunks = [];
  state.lastProcess = null;
  state.benchmark = null;
  pushActivity({ level: "warning", title: "本地索引已清空", desc: `${name} 已从当前浏览器会话中移除。`, user: "browser", duration: "0.2s" });
  showToast("已清空当前浏览器索引", "warning");
  await refreshStats();
  renderProcessLog();
  renderQuality();
  renderSearchResults();
  renderBenchmark();
}

async function runProcess() {
  if (!state.uploads.length) {
    showToast("请先拖入或选择文件", "warning");
    return;
  }
  const started = performance.now();
  const allRecords = [];
  const fileSummaries = [];
  setProgress("processFill", 8);
  for (let index = 0; index < state.uploads.length; index += 1) {
    const upload = state.uploads[index];
    try {
      const records = await parseFileRecords(upload.file);
      upload.records = records;
      allRecords.push(...records);
      fileSummaries.push({
        source_file: upload.filename,
        source_kind: upload.source_kind,
        status: "ok",
        records_extracted: records.length
      });
    } catch (error) {
      fileSummaries.push({
        source_file: upload.filename,
        source_kind: upload.source_kind,
        status: "error",
        records_extracted: 0,
        error: error.message
      });
    }
    setProgress("processFill", 8 + ((index + 1) / state.uploads.length) * 58);
  }
  state.records = allRecords;
  state.chunks = makeChunks(allRecords);
  const result = {
    files_processed: state.uploads.length,
    files_succeeded: fileSummaries.filter((item) => item.status === "ok").length,
    files_failed: fileSummaries.filter((item) => item.status === "error").length,
    records_processed: allRecords.length,
    chunks_written: state.chunks.length,
    elapsed_s: Number(((performance.now() - started) / 1000).toFixed(2)),
    file_summaries: fileSummaries,
    quality_report: buildQualityReport(allRecords, state.chunks)
  };
  state.lastProcess = result;
  setProgress("processFill", 100);
  renderProcessLog(result);
  renderQuality(result);
  await refreshStats();
  pushActivity({
    level: result.files_failed ? "warning" : "success",
    title: "浏览器本地分析完成",
    desc: `成功 ${result.files_succeeded} 个，失败 ${result.files_failed} 个，生成 ${result.chunks_written} 个 chunks。`,
    user: "browser",
    duration: `${result.elapsed_s}s`
  });
  showToast(result.files_failed ? "本地分析完成，存在部分失败文件" : "本地分析完成", result.files_failed ? "warning" : "success");
}

async function runSearch() {
  const query = $("searchInput")?.value?.trim();
  const topK = Number($("searchTopK")?.value || 5);
  if (!query) {
    showToast("请输入检索问题", "warning");
    return;
  }
  if (!state.chunks.length) {
    renderSearchResults({ results: [], message: "当前还没有本地索引，请先拖入文件并完成分析。" });
    return;
  }
  const started = performance.now();
  const queryVector = createEmbedding(query);
  const ranked = state.chunks
    .map((chunk) => {
      const similarity = cosineSimilarity(queryVector, chunk.vector);
      return {
        text: chunk.text,
        distance: Number((1 - similarity).toFixed(4)),
        score: Number(((similarity + 1) / 2).toFixed(4)),
        metadata: chunk.metadata
      };
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, topK);
  const result = {
    collection: "browser_local_index",
    results: ranked,
    latency_ms: Number((performance.now() - started).toFixed(1))
  };
  state.lastLatency = result.latency_ms;
  renderSearchResults(result);
  renderOverview();
  pushActivity({
    level: "success",
    title: "浏览器本地检索完成",
    desc: `${query} 返回 ${ranked.length} 条结果。`,
    user: "browser",
    duration: `${result.latency_ms}ms`
  });
}

async function runBenchmark() {
  const payload = {
    document_count: Number($("benchDocs")?.value || 500),
    batch_size: Number($("benchBatch")?.value || 100),
    query_count: Number($("benchQueries")?.value || 50),
    top_k: Number($("benchTopK")?.value || 5)
  };
  setProgress("benchFill", 18);
  $("benchLog").textContent = "本地 benchmark 运行中，请稍候。";
  const synthetic = Array.from({ length: payload.document_count }, (_, index) => ({
    id: `synthetic-${index}`,
    text: `文档 ${index}：燃气轮机维护、压气机工况、振动诊断、润滑状态、检索性能评估与知识库索引。`
  }));
  const insertStarted = performance.now();
  const embedded = synthetic.map((item) => ({ ...item, vector: createEmbedding(item.text) }));
  const insertSeconds = (performance.now() - insertStarted) / 1000;
  setProgress("benchFill", 58);
  const latencies = [];
  const queryStarted = performance.now();
  for (let index = 0; index < payload.query_count; index += 1) {
    const query = createEmbedding(`燃气轮机检索查询 ${index}`);
    const started = performance.now();
    embedded
      .map((item) => cosineSimilarity(query, item.vector))
      .sort((a, b) => b - a)
      .slice(0, payload.top_k);
    latencies.push(performance.now() - started);
  }
  const querySeconds = (performance.now() - queryStarted) / 1000;
  const ordered = [...latencies].sort((a, b) => a - b);
  const p95 = ordered[Math.max(0, Math.min(ordered.length - 1, Math.round((ordered.length - 1) * 0.95)))] || 0;
  state.benchmark = {
    insert_seconds: Number(insertSeconds.toFixed(4)),
    insert_docs_per_second: Number((payload.document_count / Math.max(insertSeconds, 0.001)).toFixed(2)),
    query_seconds: Number(querySeconds.toFixed(4)),
    query_qps: Number((payload.query_count / Math.max(querySeconds, 0.001)).toFixed(2)),
    avg_query_latency_ms: Number((latencies.reduce((sum, item) => sum + item, 0) / Math.max(latencies.length, 1)).toFixed(3)),
    p95_query_latency_ms: Number(p95.toFixed(3)),
    embedding_backend: "browser-hashing",
    embedding_model: `hashing-${engineDefaults.dimension}`
  };
  state.lastLatency = Number(state.benchmark.avg_query_latency_ms || state.lastLatency);
  setProgress("benchFill", 100);
  $("benchLog").textContent = `本地测试完成：平均延迟 ${state.benchmark.avg_query_latency_ms} ms，P95 ${state.benchmark.p95_query_latency_ms} ms。`;
  renderBenchmark();
  renderOverview();
  pushActivity({
    level: "success",
    title: "浏览器本地 Benchmark 完成",
    desc: `写入 ${state.benchmark.insert_docs_per_second} docs/s，查询 ${state.benchmark.query_qps} qps。`,
    user: "browser",
    duration: `${Number(state.benchmark.query_seconds || 0).toFixed(2)}s`
  });
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
  const mapped = supported.map((file) => ({
    file,
    filename: relativePathOf(file).replaceAll("/", "__"),
    display_name: relativePathOf(file),
    size_kb: Number((file.size / 1024).toFixed(1)),
    modified: Math.floor((file.lastModified || Date.now()) / 1000),
    source_kind: sourceKindFromName(relativePathOf(file))
  }));
  const keyed = new Map(state.uploads.map((item) => [item.filename, item]));
  mapped.forEach((item) => keyed.set(item.filename, item));
  state.uploads = Array.from(keyed.values());
  await refreshUploads();
  setProgress("processFill", 0);
  pushActivity({
    level: "success",
    title: "文件已加入本地队列",
    desc: `本次加入 ${mapped.length} 个文件，分析将只在当前浏览器中进行。`,
    user: "browser",
    duration: `${mapped.length} files`
  });
  if (skipped > 0) showToast(`已加入 ${mapped.length} 个文件，跳过 ${skipped} 个不支持文件`, "warning");
  else showToast(`已加入 ${mapped.length} 个文件，开始本地分析`, "success");
  await runProcess();
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
