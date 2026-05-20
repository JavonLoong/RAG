if (globalThis.pdfjsLib?.GlobalWorkerOptions) {
  globalThis.pdfjsLib.GlobalWorkerOptions.workerSrc = "https://cdn.jsdelivr.net/npm/pdfjs-dist@2.16.105/build/pdf.worker.min.js";
}

const FORCE_LOCAL_RUNTIME = window.location.protocol === "file:" || /\.github\.io$/i.test(window.location.hostname);
const API_BASE = "";
const LOCAL_COLLECTION_NAME = "browser_local_index";
const ENGINE_DEFAULTS = { chunkSize: 680, overlap: 120, dimension: 384 };

const SOURCE_LABELS = {
  PDF: "PDF",
  Text: "文本",
  JSON: "JSON",
  Markdown: "Markdown",
  Code: "??",
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
  Code: "rgba(15, 23, 42, 0.82)",
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

const JSON_TEXT_KEYS = new Set(["text", "content", "body", "description", "summary", "abstract", "caption", "paragraph", "sentence", "question", "answer", "source", "input", "output"]);
const CODE_EXTENSIONS = new Set(["py", "js", "mjs", "cjs", "ts", "tsx", "jsx", "java", "c", "cc", "cpp", "cxx", "h", "hh", "hpp", "hxx", "cs", "go", "rs", "php", "rb", "swift", "kt", "kts", "scala", "sql", "sh", "bash", "zsh", "ps1", "bat", "cmd", "html", "htm", "css", "scss", "sass", "less", "xml", "yaml", "yml", "toml", "ini", "cfg", "conf", "properties", "vue", "svelte"]);
const SUPPORTED_EXTENSIONS = new Set(["json", "jsonl", "ndjson", "ipynb", "pdf", "docx", "txt", "md", "markdown", "csv", "tsv", "log", ...CODE_EXTENSIONS]);
const DEFAULT_STATS = { status: "idle", collections: [], total_documents: 0, total_tokens_estimate: 0, storage_size_mb: 0, embedding_dim: ENGINE_DEFAULTS.dimension, source_type_breakdown: {} };
const PUBLIC_DEMO_COLLECTION = "gas_turbine_ocr_demo_snapshot";
const PUBLIC_DEMO_UPDATED_AT = 1779033600;
const PUBLIC_DEMO_FILES = [
  { filename: "ocr_ready__gas_turbine_combustion_3rd.txt", display_name: "第一梯队_OCR质量较放心_4本/燃气涡轮发动机燃烧 第3版.txt", size_kb: 9120, records: 442, chunks: 760, low_confidence: 1, avg_confidence: 0.724 },
  { filename: "ocr_ready__advanced_gas_turbine_combustor.txt", display_name: "第一梯队_OCR质量较放心_4本/先进燃气轮机燃烧室.txt", size_kb: 12680, records: 603, chunks: 980, low_confidence: 5, avg_confidence: 0.714 },
  { filename: "ocr_ready__gas_turbine_principle_structure_application_1.txt", display_name: "第一梯队_OCR质量较放心_4本/燃气轮机原理、结构与应用 上.txt", size_kb: 10140, records: 485, chunks: 820, low_confidence: 0, avg_confidence: 0.715 },
  { filename: "ocr_ready__nanjing_gas_turbine_research_institute.txt", display_name: "第一梯队_OCR质量较放心_4本/燃气轮机（南京燃气轮机研究所编）.txt", size_kb: 1420, records: 62, chunks: 95, low_confidence: 1, avg_confidence: 0.764 }
];
const PUBLIC_DEMO_STATS = {
  status: "public-demo",
  collections: [{
    name: PUBLIC_DEMO_COLLECTION,
    count: 2655,
    estimated_tokens: 1186000,
    estimated_chars: 1740000,
    source_type_counts: { PDF: 4, Text: 4, JSON: 2 },
    sources: PUBLIC_DEMO_FILES.map((item) => item.display_name)
  }],
  total_documents: 4,
  total_tokens_estimate: 1186000,
  storage_size_mb: 33.56,
  embedding_dim: ENGINE_DEFAULTS.dimension,
  source_type_breakdown: { PDF: 4, Text: 4, JSON: 2 }
};
const PUBLIC_DEMO_SEARCH_RESULTS = [
  {
    text: "燃气轮机燃烧室的主要问题包括稳定燃烧、点火、燃烧效率、温度场均匀性以及污染物排放控制。检索时应同时保留原文证据和页码，便于后续人工复核。",
    score: 0.842,
    distance: 0.158,
    metadata: { filename: "先进燃气轮机燃烧室.txt", source_kind: "Text", chunk_index: 128, record_id: "demo-advanced-combustor-p128", estimated_tokens: 96, page_nums: "128" }
  },
  {
    text: "OCR 后的扫描书先进入文本块，再按 chunk 切分，随后进入向量检索或知识图谱抽取。两栏版面、低置信度页和公式密集页需要单独标记风险。",
    score: 0.811,
    distance: 0.189,
    metadata: { filename: "燃气涡轮发动机燃烧 第3版.txt", source_kind: "Text", chunk_index: 64, record_id: "demo-combustion-p064", estimated_tokens: 88, page_nums: "64" }
  },
  {
    text: "知识图谱抽取阶段更关注实体、关系、属性和 evidence 的一致性。关系粒度过粗会丢信息，过细则接近句子谓语翻译，后续检索价值有限。",
    score: 0.786,
    distance: 0.214,
    metadata: { filename: "KG / GraphRAG POC 记录.json", source_kind: "JSON", chunk_index: 12, record_id: "demo-kg-poc-012", estimated_tokens: 82, page_nums: "-" }
  }
];

const state = {
  online: false,
  localMode: FORCE_LOCAL_RUNTIME,
  publicDemo: false,
  version: "",
  page: "overview",
  stats: null,
  primaryCollection: "",
  primaryStats: null,
  uploads: [],
  pendingUploads: [],
  processedUploads: [],
  records: [],
  chunks: [],
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

function normalizeText(value) {
  return String(value ?? "")
    .replace(/\r\n/g, "\n")
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function stripBom(text) {
  return String(text ?? "").replace(/^\uFEFF/, "");
}

function decodeArrayBuffer(buffer, encoding) {
  try {
    return new TextDecoder(encoding, { fatal: false }).decode(buffer);
  } catch {
    return "";
  }
}

function hasUtf16Bom(bytes) {
  return bytes?.length >= 2 && (
    (bytes[0] === 0xFF && bytes[1] === 0xFE) ||
    (bytes[0] === 0xFE && bytes[1] === 0xFF)
  );
}

function scoreDecodedText(text) {
  const candidate = stripBom(String(text ?? ""));
  if (!candidate.trim()) return Number.NEGATIVE_INFINITY;
  const total = candidate.length || 1;
  const replacementCount = (candidate.match(/\uFFFD/g) || []).length;
  const nullCount = (candidate.match(/\u0000/g) || []).length;
  const controlCount = (candidate.match(/[\u0001-\u0008\u000B\u000C\u000E-\u001F]/g) || []).length;
  const readableCount = (candidate.match(/[\p{L}\p{N}\p{P}\p{S}\s]/gu) || []).length;
  const cjkCount = (candidate.match(/[\u3400-\u9FFF]/g) || []).length;
  return (readableCount / total) + Math.min(cjkCount / total, 0.24) - ((replacementCount * 5) + (nullCount * 5) + (controlCount * 3)) / total;
}

function inferPreferredEncodings(buffer) {
  const bytes = buffer instanceof Uint8Array ? buffer : new Uint8Array(buffer);
  if (hasUtf16Bom(bytes)) return ["utf-16le", "utf-8", "gb18030", "big5"];
  const probeLength = Math.min(bytes.length, 128);
  let oddNulls = 0;
  let evenNulls = 0;
  for (let index = 0; index < probeLength; index += 1) {
    if (bytes[index] !== 0) continue;
    if (index % 2 === 0) evenNulls += 1;
    else oddNulls += 1;
  }
  if (oddNulls >= 8 && oddNulls > evenNulls * 3) return ["utf-16le", "utf-8", "gb18030", "big5"];
  return ["utf-8", "gb18030", "big5", "utf-16le"];
}

async function readFileTextSafely(file) {
  const buffer = await file.arrayBuffer();
  const best = inferPreferredEncodings(buffer)
    .map((encoding) => ({ encoding, text: decodeArrayBuffer(buffer, encoding) }))
    .filter((candidate) => candidate.text)
    .sort((a, b) => scoreDecodedText(b.text) - scoreDecodedText(a.text))[0];
  return stripBom(best?.text || "");
}

async function parseJsonWithEncodingFallback(file) {
  const buffer = await file.arrayBuffer();
  const attempts = inferPreferredEncodings(buffer)
    .map((encoding) => ({ encoding, text: stripBom(decodeArrayBuffer(buffer, encoding)) }))
    .filter((candidate) => candidate.text);
  let lastError = null;
  for (const candidate of attempts) {
    try {
      return JSON.parse(candidate.text);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError || new Error("JSON 解析失败");
}

function pushUniqueLine(lines, seen, text) {
  const cleaned = normalizeText(text);
  if (!cleaned || cleaned.length < 2) return;
  if (seen.has(cleaned)) return;
  seen.add(cleaned);
  lines.push(cleaned);
}

function looksLikeAnnotationTask(value) {
  return !!value && typeof value === "object" && (
    Array.isArray(value.annotations) ||
    Array.isArray(value.predictions)
  );
}

function extractAnnotationPayload(payload) {
  const tasks = Array.isArray(payload) ? payload : [payload];
  const lines = [];
  const seen = new Set();
  tasks.forEach((task) => {
    const filename = normalizeText(task?.data?.filename || "");
    if (filename) pushUniqueLine(lines, seen, filename);
    const groups = [
      ...(Array.isArray(task?.annotations) ? task.annotations : []),
      ...(Array.isArray(task?.predictions) ? task.predictions : [])
    ];
    groups.forEach((group) => {
      const results = Array.isArray(group?.result) ? group.result : [];
      results.forEach((item) => {
        const values = item?.value || {};
        const textCandidates = [
          ...(Array.isArray(values.text) ? values.text : []),
          ...(Array.isArray(values.choices) ? values.choices : []),
          ...(Array.isArray(values.labels) ? values.labels : [])
        ];
        textCandidates.forEach((entry) => pushUniqueLine(lines, seen, entry));
      });
    });
  });
  return lines;
}

function flattenMeaningfulJson(value, lines = [], seen = new Set()) {
  if (value == null) return lines;
  if (typeof value === "string") {
    pushUniqueLine(lines, seen, value);
    return lines;
  }
  if (typeof value === "number" || typeof value === "boolean") return lines;
  if (Array.isArray(value)) {
    value.forEach((item) => flattenMeaningfulJson(item, lines, seen));
    return lines;
  }
  if (typeof value === "object") {
    Object.entries(value).forEach(([key, nested]) => {
      const keyName = String(key || "").toLowerCase();
      if (JSON_TEXT_KEYS.has(keyName)) {
        flattenMeaningfulJson(nested, lines, seen);
        return;
      }
      if (["title", "heading", "name", "section", "chapter", "keywords"].includes(keyName)) {
        flattenMeaningfulJson(nested, lines, seen);
      }
      if (nested && typeof nested === "object") flattenMeaningfulJson(nested, lines, seen);
    });
  }
  return lines;
}

function extractJsonTextLines(payload) {
  if (looksLikeAnnotationTask(payload) || (Array.isArray(payload) && payload.some(looksLikeAnnotationTask))) {
    return extractAnnotationPayload(payload);
  }
  return flattenMeaningfulJson(payload);
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

function createEmbedding(text, dimension = ENGINE_DEFAULTS.dimension) {
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

function relativePathOf(file) {
  return file.webkitRelativePath || file.__relativePath || file.relativePath || file.name;
}

function fileExtension(name) {
  const parts = String(name || "").toLowerCase().split(".");
  return parts.length > 1 ? parts.pop() : "";
}

function splitTextWithOverlap(text, chunkSize = ENGINE_DEFAULTS.chunkSize, overlap = ENGINE_DEFAULTS.overlap) {
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

function parseTabularText(text, delimiter) {
  const parsed = globalThis.Papa?.parse(text, { delimiter, skipEmptyLines: true })?.data || [];
  if (!parsed.length) return "";
  const header = parsed[0];
  const rows = parsed.slice(1).map((row, rowIndex) => {
    const pairs = row.map((cell, index) => `${header[index] || `字段 ${index + 1}`}: ${normalizeText(cell)}`).join(" | ");
    return `第 ${rowIndex + 1} 行: ${pairs}`;
  });
  return normalizeText([`字段: ${header.join(" | ")}`, ...rows].join("\n\n"));
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
  const payload = await parseJsonWithEncodingFallback(file);
  const text = normalizeText(extractJsonTextLines(payload).join("\n\n"));
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
  const text = normalizeText(await readFileTextSafely(file));
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
  const text = parseTabularText(await readFileTextSafely(file), delimiter);
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
      const tokens = Array.from(new Set(tokenize(piece)));
      chunks.push({
        chunk_id: `${record.record_id}::${index}`,
        text: piece,
        vector,
        tokens,
        normalizedText: piece.toLowerCase(),
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
  const issues = docs.filter((item) => item.short_blocks > 0).map((item) => `文档 ${item.doc_id}: ${item.short_blocks} 个极短文本块（少于 5 个字符）`);
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


function cloneDefaultStats() { return typeof structuredClone === "function" ? structuredClone(DEFAULT_STATS) : JSON.parse(JSON.stringify(DEFAULT_STATS)); }
function clonePublicDemoStats() { return typeof structuredClone === "function" ? structuredClone(PUBLIC_DEMO_STATS) : JSON.parse(JSON.stringify(PUBLIC_DEMO_STATS)); }
function sourceKindFromName(name) { const ext = fileExtension(name); if (["json", "ipynb"].includes(ext)) return "JSON"; if (ext === "pdf") return "PDF"; if (ext === "docx") return "DOCX"; if (ext === "md" || ext === "markdown") return "Markdown"; if (ext === "csv") return "CSV"; if (ext === "tsv") return "TSV"; if (ext === "log") return "Log"; if (CODE_EXTENSIONS.has(ext)) return "Code"; return "Text"; }
function purgeLocalVectorsByFilename(filenames) { const selected = new Set((filenames || []).filter(Boolean)); if (!selected.size) return; state.records = state.records.filter((record) => !selected.has(record.stored_filename)); state.chunks = state.chunks.filter((chunk) => !selected.has(chunk.metadata?.stored_filename)); state.lastSearch = null; }
function buildLocalStats() { if (!state.chunks.length) return cloneDefaultStats(); const byKind = {}; state.chunks.forEach((chunk) => { const kind = chunk.metadata?.source_kind || "Other"; byKind[kind] = (byKind[kind] || 0) + 1; }); const totalTokens = state.chunks.reduce((sum, chunk) => sum + Number(chunk.metadata?.estimated_tokens || 0), 0); const totalChars = state.chunks.reduce((sum, chunk) => sum + Number(chunk.text?.length || 0), 0); const storageBytes = state.uploads.reduce((sum, item) => sum + Number(item.file?.size || 0), 0) + state.chunks.reduce((sum, chunk) => sum + Number(chunk.text?.length || 0) * 2 + Number(chunk.vector?.byteLength || 0), 0); const sources = getProcessedUploads().map((item) => item.display_name || item.filename); return { status: "ok", collections: [{ name: LOCAL_COLLECTION_NAME, count: state.chunks.length, estimated_tokens: totalTokens, estimated_chars: totalChars, source_type_counts: byKind, sources }], total_documents: state.records.length, total_tokens_estimate: totalTokens, storage_size_mb: Number((storageBytes / (1024 * 1024)).toFixed(3)), embedding_dim: ENGINE_DEFAULTS.dimension, source_type_breakdown: byKind }; }

function buildPublicDemoUploads() {
  return PUBLIC_DEMO_FILES.map((item, index) => ({
    filename: item.filename,
    display_name: item.display_name,
    size_kb: item.size_kb,
    modified: PUBLIC_DEMO_UPDATED_AT - ((PUBLIC_DEMO_FILES.length - index) * 3600),
    uploaded_at: PUBLIC_DEMO_UPDATED_AT - ((PUBLIC_DEMO_FILES.length - index) * 3600),
    processed_at: PUBLIC_DEMO_UPDATED_AT - ((PUBLIC_DEMO_FILES.length - index) * 1800),
    source_kind: "Text",
    status: "processed",
    last_collection: PUBLIC_DEMO_COLLECTION,
    last_records: item.records,
    last_chunks: item.chunks,
    last_error: null
  }));
}

function buildPublicDemoProcessResult() {
  const records = PUBLIC_DEMO_FILES.reduce((sum, item) => sum + item.records, 0);
  const chunks = PUBLIC_DEMO_FILES.reduce((sum, item) => sum + item.chunks, 0);
  return {
    requested_filenames: PUBLIC_DEMO_FILES.map((item) => item.filename),
    records_processed: records,
    chunks_written: chunks,
    files_succeeded: PUBLIC_DEMO_FILES.length,
    files_failed: 0,
    elapsed_s: 184.6,
    skipped_already_processed: [],
    file_summaries: PUBLIC_DEMO_FILES.map((item) => ({
      source_file: item.filename,
      source_kind: "Text",
      status: "ok",
      records_extracted: item.records
    })),
    quality_report: {
      chunks: { total_chunks: chunks, avg_length: 655, min_length: 118, max_length: 914 },
      documents: PUBLIC_DEMO_FILES.map((item, index) => ({
        doc_id: index + 1,
        filenames: [item.filename],
        block_count: item.records,
        short_blocks: item.low_confidence,
        label_distribution: { ocr_page: item.records, low_confidence: item.low_confidence }
      })),
      issues: [
        "公开页只展示质量较稳定的 OCR 文本样例，不包含完整 1.31G 原始材料。",
        "两栏页、公式密集页和低置信度页仍需要后续复核。"
      ],
      issue_count: 2
    }
  };
}

function activatePublicDemoSnapshot() {
  state.publicDemo = true;
  state.localMode = true;
  state.online = true;
  state.version = "public-demo";
  state.stats = clonePublicDemoStats();
  state.primaryCollection = PUBLIC_DEMO_COLLECTION;
  state.primaryStats = { record_count: 1592, chunk_count: 2655 };
  state.uploads = buildPublicDemoUploads();
  state.pendingUploads = [];
  state.processedUploads = state.uploads.slice();
  state.lastProcess = buildPublicDemoProcessResult();
  state.benchmark = {
    collection: PUBLIC_DEMO_COLLECTION,
    insert_seconds: 184.6,
    insert_docs_per_second: 8.62,
    query_seconds: 0.48,
    query_qps: 20.83,
    avg_query_latency_ms: 46.2,
    p95_query_latency_ms: 71.5,
    embedding_backend: "snapshot",
    embedding_model: `hash-${ENGINE_DEFAULTS.dimension}d demo`
  };
  state.timeline = [
    { reason: "ocr", label: "OCR", docs: 4, tokens: 320000, collections: 1, latency: 0, pdf: 4, text: 0, json: 0, other: 0 },
    { reason: "chunk", label: "分块", docs: 4, tokens: 780000, collections: 1, latency: 0, pdf: 4, text: 4, json: 0, other: 0 },
    { reason: "index", label: "索引", docs: 4, tokens: 1186000, collections: 1, latency: 46.2, pdf: 4, text: 4, json: 2, other: 0 }
  ];
  state.activity = [
    { id: "demo-1", level: "success", title: "公开演示快照", detail: "已展示 4 本 OCR 质量较放心的燃气轮机材料。", at: Date.now() - 1000 * 60 * 8 },
    { id: "demo-2", level: "success", title: "OCR 质量检查", detail: "总页数 5483 页已完成，公开页先放较稳定样例。", at: Date.now() - 1000 * 60 * 16 },
    { id: "demo-3", level: "warning", title: "后端未部署到 Pages", detail: "GitHub Pages 只托管静态页，真实 ChromaDB 需要单独后端。", at: Date.now() - 1000 * 60 * 25 }
  ];
}

async function refreshPublicDemoStats() {
  state.stats = clonePublicDemoStats();
  state.primaryCollection = PUBLIC_DEMO_COLLECTION;
  state.primaryStats = { record_count: 1592, chunk_count: 2655 };
  rememberTimeline("stats");
  renderCollectionSpectrum();
  renderCollectionList();
  renderTrendChart();
  renderSummaryMetrics();
}

function buildLocalUploadItem(file) {
  const displayName = relativePathOf(file);
  const now = Math.floor(Date.now() / 1000);
  return {
    file,
    filename: displayName.split("\\").join("/").split("/").join("__"),
    display_name: displayName,
    size_kb: Number((file.size / 1024).toFixed(1)),
    modified: Math.floor((file.lastModified || Date.now()) / 1000),
    uploaded_at: now,
    processed_at: null,
    source_kind: sourceKindFromName(displayName),
    status: "uploaded",
    last_collection: null,
    last_records: 0,
    last_chunks: 0,
    last_error: null
  };
}

function upsertUploadItem(item) { state.uploads = [item, ...(state.uploads || []).filter((entry) => entry.filename !== item.filename)]; }
function refreshLocalUploadBuckets() { state.uploads = Array.isArray(state.uploads) ? state.uploads.slice().sort((a, b) => Number(b.uploaded_at || b.modified || 0) - Number(a.uploaded_at || a.modified || 0)) : []; state.pendingUploads = state.uploads.filter((item) => item.status !== "processed"); state.processedUploads = state.uploads.filter((item) => item.status === "processed"); syncUploadSelections(); }
async function refreshLocalStats() { state.stats = buildLocalStats(); state.primaryCollection = choosePrimaryCollection(state.stats.collections); state.primaryStats = state.primaryCollection ? { record_count: state.records.length, chunk_count: state.chunks.length } : null; rememberTimeline("stats"); renderCollectionSpectrum(); renderCollectionList(); renderTrendChart(); renderSummaryMetrics(); }

async function deleteLocalUpload(filename, options = {}) {
  state.uploads = (state.uploads || []).filter((item) => item.filename !== filename);
  if (options.purgeVectors) {
    purgeLocalVectorsByFilename([filename]);
    await refreshLocalStats();
  }
  refreshLocalUploadBuckets();
  renderUploads();
  renderProcessedUploads();
  renderProcessSummary();
  renderQualityReport();
  renderSearchResults();
  const label = splitUploadPath(uploadDisplayName(filename)).file;
  addActivity("success", options.purgeVectors ? "Processed file removed" : "Removed from upload directory", label);
  showToast(options.purgeVectors ? `Removed ${label} and cleared local index.` : `Removed ${label}.`, "success");
}


async function deleteLocalProcessedUploads(filenames) {
  const selected = Array.from(new Set((filenames || []).filter(Boolean)));
  if (!selected.length) {
    showToast("Select processed files first.", "warning");
    return;
  }
  if (!window.confirm(`Delete ${selected.length} processed files and clear their local vectors?`)) return;
  purgeLocalVectorsByFilename(selected);
  state.uploads = (state.uploads || []).filter((item) => !selected.includes(item.filename));
  state.selectedProcessedUploads.clear();
  state.processedEditMode = false;
  refreshLocalUploadBuckets();
  await refreshLocalStats();
  renderProcessSummary();
  renderQualityReport();
  renderSearchResults();
  addActivity("success", "Processed files removed", `Deleted ${selected.length} files and cleared local vectors.`);
  showToast(`Deleted ${selected.length} processed files.`, "success");
}


async function deleteLocalCollection(name) {
  state.records = [];
  state.chunks = [];
  state.timeline = [];
  state.lastProcess = null;
  state.lastSearch = null;
  state.expandedResults = new Set();
  state.benchmark = null;
  state.uploads = (state.uploads || []).map((item) => ({
    ...item,
    status: "uploaded",
    processed_at: null,
    last_collection: null,
    last_records: 0,
    last_chunks: 0,
    last_error: null
  }));
  refreshLocalUploadBuckets();
  await refreshLocalStats();
  renderProcessSummary();
  renderQualityReport();
  renderSearchResults();
  renderBenchmark();
  addActivity("warning", "Local index cleared", `${name} was removed from this browser session.`);
  showToast("Local index cleared.", "warning");
}


async function runLocalProcess() {
  const selectedItems = getPendingUploads().filter((item) => state.selectedUploads.has(item.filename));
  if (!selectedItems.length) {
    showToast("Select files to process first.", "warning");
    return;
  }
  if (els.btnProcess) {
    els.btnProcess.disabled = true;
    els.btnProcess.dataset.busy = "true";
  }
  if (els.processFill) els.processFill.style.width = "18%";
  if (els.processLog) renderEmpty(els.processLog, "Browser-local processing is running...");
  const started = performance.now();
  const fileSummaries = [];
  const nextRecords = [];
  const nextChunks = [];
  const succeeded = [];
  let failed = 0;
  try {
    addActivity("warning", "Local processing started", `Processing ${selectedItems.length} selected files.`);
    for (let index = 0; index < selectedItems.length; index += 1) {
      const item = selectedItems[index];
      try {
        const parsed = await parseFileRecords(item.file);
        const records = parsed.map((record) => ({
          ...record,
          stored_filename: item.filename,
          filename: item.display_name || record.filename || item.filename,
          source_file: item.display_name || record.source_file || item.filename,
          source_kind: record.source_kind || item.source_kind
        }));
        const chunks = makeChunks(records);
        nextRecords.push(...records);
        nextChunks.push(...chunks);
        succeeded.push(item.filename);
        fileSummaries.push({ source_file: item.filename, source_kind: item.source_kind, status: "ok", records_extracted: records.length, error: null });
        Object.assign(item, { status: "processed", processed_at: Math.floor(Date.now() / 1000), last_collection: LOCAL_COLLECTION_NAME, last_records: records.length, last_chunks: chunks.length, last_error: null });
      } catch (error) {
        failed += 1;
        fileSummaries.push({ source_file: item.filename, source_kind: item.source_kind, status: "error", records_extracted: 0, error: error.message || String(error) });
        Object.assign(item, { status: "uploaded", processed_at: null, last_collection: null, last_records: 0, last_chunks: 0, last_error: error.message || String(error) });
      }
      if (els.processFill) els.processFill.style.width = `${Math.min(100, 18 + Math.round(((index + 1) / selectedItems.length) * 82))}%`;
    }
    purgeLocalVectorsByFilename(succeeded);
    state.records = [...state.records, ...nextRecords];
    state.chunks = [...state.chunks, ...nextChunks];
    refreshLocalUploadBuckets();
    state.selectedUploads.clear();
    state.lastProcess = {
      collection: LOCAL_COLLECTION_NAME,
      requested_filenames: selectedItems.map((item) => item.filename),
      skipped_already_processed: [],
      files_succeeded: succeeded.length,
      files_failed: failed,
      records_processed: nextRecords.length,
      chunks_written: nextChunks.length,
      elapsed_s: Number(((performance.now() - started) / 1000).toFixed(2)),
      file_summaries: fileSummaries,
      quality_report: buildQualityReport(nextRecords, nextChunks),
      embedding_backend: "browser-local"
    };
    await refreshLocalStats();
    renderUploads();
    renderProcessedUploads();
    renderProcessSummary();
    renderQualityReport();
    renderSummaryMetrics();
    addActivity(failed ? "warning" : "success", "Local processing finished", `Succeeded on ${succeeded.length} files and generated ${nextChunks.length} chunks.`);
    showToast(`Local processing finished. Success: ${succeeded.length}, failed: ${failed}.`, failed ? "warning" : "success");
  } catch (error) {
    if (els.processFill) els.processFill.style.width = "0%";
    addActivity("danger", "Processing failed", error.message || String(error));
    renderProcessSummary();
    showToast(error.message || "Processing failed.", "danger");
  } finally {
    if (els.btnProcess) {
      delete els.btnProcess.dataset.busy;
      els.btnProcess.disabled = false;
    }
    renderUploads();
  }
}


async function runLocalSearch() {
  const query = String(els.searchInput?.value || "").trim();
  if (!query) {
    showToast("Enter a search query first.", "warning");
    return;
  }
  if (els.searchMeta) els.searchMeta.textContent = "Searching locally...";
  const topK = Number(els.searchTopK?.value || 5);
  const started = performance.now();
  if (state.publicDemo && !state.chunks.length) {
    const results = PUBLIC_DEMO_SEARCH_RESULTS.slice(0, topK).map((item, index) => ({
      ...item,
      score: Number(Math.max(0.1, item.score - index * 0.018).toFixed(4)),
      distance: Number(Math.min(0.99, item.distance + index * 0.018).toFixed(4))
    }));
    state.lastSearch = {
      query,
      collection: PUBLIC_DEMO_COLLECTION,
      latency_ms: Number((performance.now() - started + 38.6).toFixed(2)),
      results,
      embedding_backend: "public-demo"
    };
    rememberTimeline("search");
    renderSearchResults();
    renderTrendChart();
    renderSummaryMetrics();
    addActivity("success", "演示检索完成", `查询“${query}”返回 ${results.length} 条样例证据。`);
    showToast(`演示检索完成，返回 ${results.length} 条样例。`, "success");
    return;
  }
  if (!state.chunks.length) {
    state.lastSearch = { query, collection: LOCAL_COLLECTION_NAME, latency_ms: 0, results: [], embedding_backend: "browser-local", message: "No local index yet. Process files first." };
    renderSearchResults();
    showToast("Process files before searching.", "warning");
    return;
  }
  const queryVector = createEmbedding(query);
  const normalizedQuery = normalizeText(query).toLowerCase();
  const queryTokens = Array.from(new Set(tokenize(query))).filter((token) => token.length > 1);
  const results = state.chunks.map((chunk) => {
    const similarity = cosineSimilarity(queryVector, chunk.vector);
    const semanticScore = (similarity + 1) / 2;
    const overlapCount = queryTokens.reduce((sum, token) => sum + (chunk.tokens?.includes(token) ? 1 : 0), 0);
    const overlapScore = queryTokens.length ? overlapCount / queryTokens.length : 0;
    const phraseBonus = normalizedQuery && chunk.normalizedText.includes(normalizedQuery) ? 0.12 : 0;
    const score = Math.min(0.9999, semanticScore * 0.7 + overlapScore * 0.24 + phraseBonus);
    return { text: chunk.text, distance: Number((1 - score).toFixed(4)), score: Number(score.toFixed(4)), metadata: chunk.metadata };
  }).sort((a, b) => b.score - a.score).slice(0, topK);
  state.lastSearch = { query, collection: LOCAL_COLLECTION_NAME, latency_ms: Number((performance.now() - started).toFixed(2)), results, embedding_backend: "browser-local" };
  rememberTimeline("search");
  renderSearchResults();
  renderTrendChart();
  renderSummaryMetrics();
  addActivity(results.length ? "success" : "warning", "Local search finished", `Query ?${query}? returned ${results.length} results.`);
  showToast(`Search finished. ${results.length} results returned.`, "success");
}


async function runLocalBenchmark() {
  const payload = { document_count: Number(els.benchDocs?.value || 500), query_count: Number(els.benchQueries?.value || 50), top_k: Number(els.benchTopK?.value || 5) };
  if (els.btnBench) els.btnBench.disabled = true;
  if (els.benchFill) els.benchFill.style.width = "18%";
  if (els.benchLog) els.benchLog.textContent = "Running browser-local benchmark...";
  try {
    addActivity("warning", "Local benchmark started", `${payload.document_count} docs / ${payload.query_count} queries`);
    const synthetic = Array.from({ length: payload.document_count }, (_, i) => ({ text: `Power equipment benchmark sample ${i} with turbine, engine and maintenance content.` }));
    const insertStarted = performance.now();
    const embedded = synthetic.map((item) => ({ ...item, vector: createEmbedding(item.text) }));
    const insertSeconds = (performance.now() - insertStarted) / 1000;
    if (els.benchFill) els.benchFill.style.width = "58%";
    const latencies = [];
    const queryStarted = performance.now();
    for (let i = 0; i < payload.query_count; i += 1) {
      const query = createEmbedding(`Local benchmark query ${i}`);
      const started = performance.now();
      embedded.map((item) => cosineSimilarity(query, item.vector)).sort((a, b) => b - a).slice(0, payload.top_k);
      latencies.push(performance.now() - started);
    }
    const querySeconds = (performance.now() - queryStarted) / 1000;
    const ordered = [...latencies].sort((a, b) => a - b);
    const p95 = ordered[Math.max(0, Math.min(ordered.length - 1, Math.round((ordered.length - 1) * 0.95)))] || 0;
    state.benchmark = { collection: `${LOCAL_COLLECTION_NAME}_benchmark`, insert_seconds: Number(insertSeconds.toFixed(4)), insert_docs_per_second: Number((payload.document_count / Math.max(insertSeconds, 0.001)).toFixed(2)), query_seconds: Number(querySeconds.toFixed(4)), query_qps: Number((payload.query_count / Math.max(querySeconds, 0.001)).toFixed(2)), avg_query_latency_ms: Number((latencies.reduce((sum, value) => sum + value, 0) / Math.max(latencies.length, 1)).toFixed(3)), p95_query_latency_ms: Number(p95.toFixed(3)), embedding_backend: "browser-local", embedding_model: `hash-${ENGINE_DEFAULTS.dimension}d` };
    if (els.benchFill) els.benchFill.style.width = "100%";
    rememberTimeline("benchmark");
    renderBenchmark();
    renderTrendChart();
    renderSummaryMetrics();
    addActivity("success", "Local benchmark finished", `Average latency ${formatDecimal(state.benchmark.avg_query_latency_ms, 3)} ms.`);
    showToast("Browser-local benchmark finished.", "success");
  } catch (error) {
    if (els.benchFill) els.benchFill.style.width = "0%";
    addActivity("danger", "Benchmark failed", error.message || String(error));
    showToast(error.message || "Benchmark failed.", "danger");
  } finally {
    if (els.btnBench) els.btnBench.disabled = false;
  }
}

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
  if (normalized === "code") return "Code";
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
    else if (kind === "Text" || kind === "Markdown" || kind === "DOCX" || kind === "Log" || kind === "Code") breakdown.Text += Number(value || 0);
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
  if (state.publicDemo) {
    els.statusText.textContent = "公开演示快照已加载。GitHub Pages 只展示成果，真实 ChromaDB 需要后端服务。";
    els.refreshStamp.textContent = `Demo snapshot ${snapshotClock()}`;
    setStatusLevel("success");
  } else if (state.localMode) {
    els.statusText.textContent = "Browser-local runtime is ready. No localhost:8000 server is required.";
    els.refreshStamp.textContent = `Local session ${snapshotClock()}`;
    setStatusLevel("success");
  } else if (state.online) {
    els.statusText.textContent = `Backend connected${state.version ? ` ? v${state.version}` : ""}. Upload and retrieval are available.`;
    els.refreshStamp.textContent = `Last sync ${snapshotClock()}`;
    setStatusLevel("success");
  } else {
    els.statusText.textContent = "Backend unavailable. Start http://localhost:8000 to use server mode.";
    els.refreshStamp.textContent = "Waiting for backend";
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
  if (FORCE_LOCAL_RUNTIME) {
    if (/\.github\.io$/i.test(window.location.hostname)) activatePublicDemoSnapshot();
    else {
      state.localMode = true;
      state.online = true;
      state.version = "browser-local";
    }
    renderStatus();
    return;
  }
  try {
    const payload = await requestJson("/api/health", {}, 15000);
    state.localMode = false;
    state.online = payload.status === "ok";
    state.version = payload.version || "";
  } catch (error) {
    state.localMode = true;
    state.online = true;
    state.version = "browser-local";
  }
  renderStatus();
}

async function refreshStats() {
  if (state.publicDemo) { await refreshPublicDemoStats(); return; }
  if (state.localMode) { await refreshLocalStats(); return; }
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
  if (state.publicDemo) { state.pendingUploads = []; state.processedUploads = state.uploads.slice(); renderUploads(); renderProcessedUploads(); return; }
  if (state.localMode) { refreshLocalUploadBuckets(); renderUploads(); renderProcessedUploads(); return; }
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
  const ext = fileExtension(relativePathOf(file));
  return SUPPORTED_EXTENSIONS.has(ext);
}



async function uploadFiles(fileList) {
  if (state.publicDemo) {
    showToast("公开演示页不接收上传；真实上传需要后端服务。", "warning");
    return;
  }
  const incoming = dedupeFiles(Array.from(fileList || []));
  const files = incoming.filter(isSupportedFile);
  const skippedCount = incoming.length - files.length;
  if (!files.length) {
    showToast("No supported files were found.", "warning");
    return;
  }

  addActivity("warning", state.localMode ? "Local ingest started" : "Upload started", `Queued ${files.length} files${skippedCount ? `, skipped ${skippedCount} unsupported files` : ""}.`);
  if (state.localMode) {
    let replacedCount = 0;
    files.forEach((file, index) => {
      if (els.uploadQueueMeta) els.uploadQueueMeta.textContent = `Adding to local directory ${index + 1}/${files.length}: ${relativePathOf(file)}`;
      const nextItem = buildLocalUploadItem(file);
      const existing = (state.uploads || []).find((item) => item.filename === nextItem.filename);
      if (existing?.status === "processed") {
        purgeLocalVectorsByFilename([existing.filename]);
        replacedCount += 1;
      }
      upsertUploadItem(nextItem);
    });
    refreshLocalUploadBuckets();
    await refreshLocalStats();
    renderUploads();
    renderProcessedUploads();
    const summary = `Added ${files.length} files${replacedCount ? `, replaced ${replacedCount} previously processed files` : ""}${skippedCount ? `, skipped ${skippedCount} unsupported files` : ""}.`;
    addActivity(skippedCount ? "warning" : "success", "Local directory updated", summary);
    showToast(summary, skippedCount ? "warning" : "success");
    return;
  }

  let successCount = 0;
  let failedCount = 0;
  for (let index = 0; index < files.length; index += 1) {
    const file = files[index];
    if (els.uploadQueueMeta) {
      els.uploadQueueMeta.textContent = `Uploading ${index + 1}/${files.length}: ${relativePathOf(file)}`;
    }

    const form = new FormData();
    form.append("file", file, file.name);
    form.append("relative_path", relativePathOf(file));

    try {
      const uploaded = await requestJson("/api/upload", { method: "POST", body: form }, 120000);
      successCount += 1;
      const now = Math.floor(Date.now() / 1000);
      const nextItem = {
        filename: uploaded.filename,
        display_name: uploaded.display_name || relativePathOf(file),
        size_kb: uploaded.size_kb ?? Number((file.size / 1024).toFixed(1)),
        source_kind: uploaded.source_kind || sourceKindFromName(relativePathOf(file)),
        modified: now,
        uploaded_at: now,
        processed_at: null,
        status: "uploaded",
        last_collection: null,
        last_records: 0,
        last_chunks: 0,
        last_error: null
      };
      state.uploads = [nextItem, ...(state.uploads || []).filter((item) => item.filename !== nextItem.filename)];
      state.pendingUploads = state.uploads.filter((item) => item.status !== "processed");
      state.processedUploads = state.uploads.filter((item) => item.status === "processed");
      syncUploadSelections();
      renderUploads();
      renderProcessedUploads();
    } catch (error) {
      failedCount += 1;
      addActivity("danger", "Upload failed", `${relativePathOf(file)}: ${error.message || error}`);
    }
  }

  await refreshUploads();
  const message = `Upload complete. Success ${successCount}, failed ${failedCount}${skippedCount ? `, skipped ${skippedCount}` : ""}.`;
  addActivity(failedCount || skippedCount ? "warning" : "success", "Upload complete", message);
  showToast(message, failedCount || skippedCount ? "warning" : "success");
}

async function deleteUpload(filename, options = {}) {
  if (state.publicDemo) {
    showToast("公开演示页不删除样例文件。", "warning");
    return;
  }
  if (state.localMode) {
    await deleteLocalUpload(filename, options);
    return;
  }
  const purgeVectors = Boolean(options.purgeVectors);
  const suffix = purgeVectors ? "?purge_vectors=true" : "";
  await requestJson(`/api/uploads/${encodeURIComponent(filename)}${suffix}`, { method: "DELETE" });
  addActivity("success", purgeVectors ? "Processed file removed" : "Removed from upload directory", splitUploadPath(uploadDisplayName(filename)).file);
  if (purgeVectors) {
    await Promise.all([refreshUploads(), refreshStats()]);
  } else {
    await refreshUploads();
  }
  showToast(purgeVectors ? `Removed ${splitUploadPath(uploadDisplayName(filename)).file} and cleared vectors.` : `Removed ${splitUploadPath(uploadDisplayName(filename)).file}.`, "success");
}


async function deleteProcessedUploads(filenames) {
  if (state.publicDemo) {
    showToast("公开演示页不删除样例文件。", "warning");
    return;
  }
  if (state.localMode) {
    await deleteLocalProcessedUploads(filenames);
    return;
  }
  const selected = Array.from(new Set((filenames || []).filter(Boolean)));
  if (!selected.length) {
    showToast("Select processed files first.", "warning");
    return;
  }
  if (!window.confirm(`Delete ${selected.length} processed files and clear their vectors?`)) return;

  const result = await requestJson("/api/uploads/delete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ filenames: selected, purge_vectors: true })
  }, 120000);

  addActivity("success", "Processed files removed", `Deleted ${selected.length} files and cleared ${formatNumber(result.chunks_deleted || 0)} chunks.`);
  state.selectedProcessedUploads.clear();
  state.processedEditMode = false;
  await Promise.all([refreshUploads(), refreshStats()]);
  renderProcessSummary();
  renderQualityReport();
  renderSummaryMetrics();
  showToast(`Deleted ${selected.length} processed files.`, "success");
}

function toggleProcessedEditMode(force) {
  if (state.publicDemo) {
    showToast("公开演示页只展示成果，不编辑样例文件。", "warning");
    return;
  }
  state.processedEditMode = typeof force === "boolean" ? force : !state.processedEditMode;
  if (!state.processedEditMode) state.selectedProcessedUploads.clear();
  renderProcessedUploads();
}

async function runProcess() {
  if (state.publicDemo) {
    showToast("公开演示页已预置处理摘要；真实入库需要后端服务。", "warning");
    return;
  }
  if (state.localMode) {
    await runLocalProcess();
    return;
  }
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
  if (state.localMode) {
    await runLocalSearch();
    return;
  }
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
  if (state.publicDemo) {
    showToast("公开演示集合不能在 Pages 上删除。", "warning");
    return;
  }
  if (state.localMode) {
    await deleteLocalCollection(name);
    return;
  }
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
  if (state.publicDemo) {
    renderBenchmark();
    showToast("公开页显示的是演示压测快照。", "success");
    return;
  }
  if (state.localMode) {
    await runLocalBenchmark();
    return;
  }
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
    const dropped = await filesFromDrop(event.dataTransfer);
    await uploadFiles(dropped);
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
      state.primaryStats = state.publicDemo
        ? { record_count: 1592, chunk_count: 2655 }
        : state.localMode
          ? { record_count: state.records.length, chunk_count: state.chunks.length }
          : await requestJson(`/api/stats?collection=${encodeURIComponent(state.primaryCollection)}`);
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
  if (FORCE_LOCAL_RUNTIME && /\.github\.io$/i.test(window.location.hostname)) {
    activatePublicDemoSnapshot();
  } else {
    addActivity("warning", "前端已加载", "正在连接后端服务并同步 Chroma 统计。");
  }
  renderAll();
  await refreshAll();
}

window.addEventListener("DOMContentLoaded", init);

