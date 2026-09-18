/* Same-origin transport only. No domain authority is derived here. */
export class FmeaProblem extends Error {
  constructor(status, problem = {}) {
    super(typeof problem.detail === 'string' ? problem.detail.slice(0, 1000) : `请求失败（${status}）`);
    this.name = 'FmeaProblem';
    this.status = status;
    this.code = typeof problem.code === 'string' ? problem.code : 'FMEA_HTTP_ERROR';
    this.requestId = problem.request_id || '';
    this.traceId = problem.trace_id || '';
    this.retryable = problem.retryable === true;
  }
}

export class FmeaClient {
  #token = '';
  #etags = new Map();
  #controllers = new Set();
  constructor({origin = globalThis.location?.origin, fetchImpl = globalThis.fetch, timeoutMs = 120000} = {}) {
    this.origin = origin;
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }
  setToken(token) { this.cancel(); this.#etags.clear(); this.#token = token.trim(); }
  etag(path) { return this.#etags.get(path); }
  cancel() { for (const controller of this.#controllers) controller.abort(); }
  #url(path) {
    if (typeof path !== 'string' || !path.startsWith('/api/v1/fmea/')) throw new Error('接口路径不在 FMEA 范围内');
    const url = new URL(path, this.origin);
    if (url.origin !== this.origin || !url.pathname.startsWith('/api/v1/fmea/')) throw new Error('接口路径不在 FMEA 范围内');
    return url;
  }
  operation(path, body, etag) {
    this.#url(path);
    if (!/^"[1-9][0-9]*"$/.test(etag || '')) throw new Error('请先读取资源版本，再提交操作');
    // Serialize once: an ambiguous network retry must retain both bytes and key.
    return Object.freeze({path, body: JSON.stringify(body), etag, key: crypto.randomUUID()});
  }
  templateImportOperation(file) {
    if (!(file instanceof File) || file.size < 1 || file.size > 256 * 1024 || !/^[^/\\\u0000-\u001f]+\.(xlsx|docx)$/i.test(file.name)) {
      throw new Error('模板必须是名称安全且不超过 256 KiB 的 XLSX/DOCX 文件');
    }
    return Object.freeze({path: '/api/v1/fmea/template-drafts', file, key: crypto.randomUUID()});
  }
  async execute(operation) {
    if (operation.file) {
      if (operation.path !== '/api/v1/fmea/template-drafts') throw new Error('不支持此上传接口');
      const body = new FormData();
      body.append('file', operation.file, operation.file.name);
      return this.#request(operation.path, {method: 'POST', body, headers: {'Idempotency-Key': operation.key}});
    }
    return this.#request(operation.path, {
      method: 'POST', body: operation.body,
      headers: {'Content-Type': 'application/json', 'If-Match': operation.etag, 'Idempotency-Key': operation.key},
    });
  }
  async get(path) { return this.#request(path); }
  async page(path, cursor = null, limit = 50) {
    if (!Number.isInteger(limit) || limit < 1 || limit > 100) throw new Error('分页大小应为 1–100');
    const url = this.#url(path);
    url.searchParams.set('limit', String(limit));
    if (cursor) url.searchParams.set('cursor', cursor);
    return this.get(url.pathname + url.search);
  }
  async download(path) { return this.#request(path, {}, true); }
  async #request(path, options = {}, binary = false) {
    const url = this.#url(path);
    const controller = new AbortController();
    this.#controllers.add(controller);
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const headers = new Headers(options.headers);
      headers.set('Accept', binary ? 'application/octet-stream' : 'application/json');
      if (this.#token) headers.set('Authorization', `Bearer ${this.#token}`);
      headers.set('X-Request-ID', crypto.randomUUID());
      const response = await this.fetchImpl.call(globalThis, url.toString(), {
        ...options, headers, signal: controller.signal, credentials: 'same-origin', redirect: 'error', cache: 'no-store',
      });
      if (!response.ok) {
        let problem = {};
        try { problem = await response.json(); } catch { /* Never display an HTML proxy error. */ }
        throw new FmeaProblem(response.status, problem);
      }
      const etag = response.headers.get('ETag');
      if (etag) this.#etags.set(path, etag);
      if (binary) return {blob: await response.blob(), etag, disposition: response.headers.get('Content-Disposition')};
      const envelope = await response.json();
      if (!envelope || !Object.hasOwn(envelope, 'data')) throw new Error('接口返回了不支持的结果格式');
      return {data: envelope.data, etag, requestId: envelope.request_id, traceId: envelope.trace_id};
    } finally {
      clearTimeout(timer);
      this.#controllers.delete(controller);
    }
  }
}
