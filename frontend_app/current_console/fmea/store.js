export class WorkbenchStore extends EventTarget {
  #epoch = 0;
  constructor(client) {
    super();
    this.client = client;
    this.state = this.#empty();
  }
  #empty() { return {selection: null, context: null, resources: {}, busy: false, writing: false, error: '', notice: '', pending: null, refreshPending: null}; }
  get hasUnresolvedWrite() { return this.state.writing || this.state.pending !== null; }
  changed() { this.dispatchEvent(new Event('change')); }
  configure(selection, token) {
    if (this.hasUnresolvedWrite) throw new Error('仍有进行中或未决的写入，请先核实或重试原请求，不能切换连接');
    for (const value of Object.values(selection)) {
      if (typeof value !== 'string' || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$/.test(value)) throw new Error('资源 ID 格式不正确');
    }
    this.client.setToken(token);
    this.#epoch++;
    this.state = {...this.#empty(), selection: Object.freeze({...selection})};
    this.changed();
  }
  contextPath() { return `/api/v1/fmea/rows/${encodeURIComponent(this.state.selection.rowId)}/review-context`; }
  resource(path) { return this.state.resources[path]; }
  #accept(path, response) {
    if (path === this.contextPath()) {
      const row = response.data?.row;
      if (!row || row.row_id !== this.state.selection.rowId || row.analysis_id !== this.state.selection.analysisId) {
        throw new Error('返回的行或分析 ID 与所选资源不匹配');
      }
      this.state.context = response.data;
    }
    this.state.resources[path] = response;
  }
  #message(error) {
    if (error.name === 'AbortError') return '请求已停止；服务端任务可能仍在运行，请查询状态后再操作。';
    return `${error.code ? `${error.code}：` : ''}${error.message}${error.requestId ? `（请求 ${error.requestId}）` : ''}`;
  }
  async loadContext() { return this.read(this.contextPath()); }
  async read(path, {cursor, limit = 50} = {}) {
    const epoch = this.#epoch;
    this.state.busy = true;
    this.state.error = '';
    this.changed();
    try {
      const response = cursor !== undefined ? await this.client.page(path, cursor, limit) : await this.client.get(path);
      if (epoch !== this.#epoch) return;
      this.#accept(path, response);
      if (this.state.refreshPending === path) this.state.refreshPending = null;
      return response;
    } catch (error) {
      if (epoch === this.#epoch) this.state.error = this.#message(error);
    } finally {
      if (epoch === this.#epoch) { this.state.busy = false; this.changed(); }
    }
  }
  async submit(operation, refreshPath) {
    if (this.state.busy) return;
    if (this.state.pending && this.state.pending.operation !== operation) {
      this.state.error = '仍有未决写入，请先重试原请求；不能生成另一个幂等键提交';
      this.changed();
      return;
    }
    const epoch = this.#epoch;
    this.state.busy = true;
    this.state.writing = true;
    this.state.error = '';
    this.state.notice = '';
    this.state.refreshPending = null;
    this.changed();
    try {
      let response;
      try {
        response = await this.client.execute(operation);
      } catch (error) {
        await this.#writeFailure(error, operation, refreshPath, epoch);
        return;
      }
      if (epoch !== this.#epoch) return;
      this.state.resources[operation.path] = response;
      this.state.pending = null;
      this.state.notice = '服务端已返回成功回执；请查看资源或后续任务状态。';
      try {
        const successPath = typeof refreshPath === 'string' ? refreshPath : refreshPath?.onSuccess(response.data);
        if (successPath) {
          this.state.refreshPending = successPath;
          const fresh = await this.client.get(successPath);
          if (epoch === this.#epoch) {
            this.#accept(successPath, fresh);
            this.state.refreshPending = null;
          }
        }
      } catch (error) {
        if (epoch === this.#epoch) this.state.error = `已收到成功回执，但刷新状态失败：${this.#message(error)}`;
      }
      return response;
    } finally {
      if (epoch === this.#epoch) { this.state.writing = false; this.state.busy = false; this.changed(); }
    }
  }
  async #writeFailure(error, operation, refreshPath, epoch) {
    if (epoch !== this.#epoch) return;
    const conflict = error.status === 409 || error.status === 412;
    this.state.error = this.#message(error);
    const retryable = !error.status || error.retryable === true || error.name === 'AbortError';
    this.state.pending = retryable && !conflict ? {operation, refreshPath} : null;
    const conflictPath = typeof refreshPath === 'string' ? refreshPath : refreshPath?.onConflict;
    if (conflict && conflictPath) {
      try {
        const fresh = await this.client.get(conflictPath);
        if (epoch !== this.#epoch) return;
        this.#accept(conflictPath, fresh);
        this.state.error = `版本或状态冲突，已刷新资源。请核对后重新确认。${this.#message(error)}`;
      } catch (refreshError) {
        if (epoch === this.#epoch) this.state.error += `；刷新失败：${this.#message(refreshError)}`;
      }
    }
  }
  async retryRefresh() {
    const path = this.state.refreshPending;
    if (!path || this.state.busy) return;
    const response = await this.read(path);
    if (response) { this.state.notice = '最新状态已读取；没有重新提交写入。'; this.changed(); }
  }
  cancel() { this.client.cancel(); }
}
