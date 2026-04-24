
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

const state = {
  online: false,
  localMode: FORCE_LOCAL_RUNTIME,
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
function sourceKindFromName(name) { const ext = fileExtension(name); if (["json", "ipynb"].includes(ext)) return "JSON"; if (ext === "pdf") return "PDF"; if (ext === "docx") return "DOCX"; if (ext === "md" || ext === "markdown") return "Markdown"; if (ext === "csv") return "CSV"; if (ext === "tsv") return "TSV"; if (ext === "log") return "Log"; if (CODE_EXTENSIONS.has(ext)) return "Code"; return "Text"; }
function purgeLocalVectorsByFilename(filenames) { const selected = new Set((filenames || []).filter(Boolean)); if (!selected.size) return; state.records = state.records.filter((record) => !selected.has(record.stored_filename)); state.chunks = state.chunks.filter((chunk) => !selected.has(chunk.metadata?.stored_filename)); state.lastSearch = null; }
function buildLocalStats() { if (!state.chunks.length) return cloneDefaultStats(); const byKind = {}; state.chunks.forEach((chunk) => { const kind = chunk.metadata?.source_kind || "Other"; byKind[kind] = (byKind[kind] || 0) + 1; }); const totalTokens = state.chunks.reduce((sum, chunk) => sum + Number(chunk.metadata?.estimated_tokens || 0), 0); const totalChars = state.chunks.reduce((sum, chunk) => sum + Number(chunk.text?.length || 0), 0); const storageBytes = state.uploads.reduce((sum, item) => sum + Number(item.file?.size || 0), 0) + state.chunks.reduce((sum, chunk) => sum + Number(chunk.text?.length || 0) * 2 + Number(chunk.vector?.byteLength || 0), 0); const sources = getProcessedUploads().map((item) => item.display_name || item.filename); return { status: "ok", collections: [{ name: LOCAL_COLLECTION_NAME, count: state.chunks.length, estimated_tokens: totalTokens, estimated_chars: totalChars, source_type_counts: byKind, sources }], total_documents: state.records.length, total_tokens_estimate: totalTokens, storage_size_mb: Number((storageBytes / (1024 * 1024)).toFixed(3)), embedding_dim: ENGINE_DEFAULTS.dimension, source_type_breakdown: byKind }; }

function buildLocalUploadItem(file) {
  const displayName = relativePathOf(file);
  const now = Math.floor(Date.now() / 1000);
  return {
    file,
    filename: displayName.replaceAll("\", "/").replaceAll("/", "__"),
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
