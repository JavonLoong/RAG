(function registerAcceptancePage(global) {
  "use strict";

  global.PowerRAGPages.register({ id: "acceptance", mode: "rag", title: "验收工作台" });

  const state = {
    schema: null,
    status: null,
    artifact: null,
    handoff: null,
    mounted: false,
    loading: false,
  };

  const $ = (id) => document.getElementById(id);

  function escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function correlationId() {
    return global.crypto && typeof global.crypto.randomUUID === "function"
      ? global.crypto.randomUUID()
      : `acceptance-${Date.now()}`;
  }

  async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    headers.set("X-Correlation-ID", correlationId());
    headers.set("X-Project-ID", "default");
    const response = await fetch(path, { ...options, headers });
    const contentType = response.headers.get("content-type") || "";
    const payload = contentType.includes("application/json")
      ? await response.json()
      : await response.text();
    if (!response.ok) {
      const detail = payload?.detail || payload;
      const message = detail?.message || detail?.code || detail || `HTTP ${response.status}`;
      const error = new Error(String(message));
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return payload;
  }

  function setBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalHtml = button.innerHTML;
      button.disabled = true;
      button.textContent = label;
    } else {
      button.disabled = false;
      if (button.dataset.originalHtml) button.innerHTML = button.dataset.originalHtml;
    }
  }

  function artifactSpec(key) {
    return (state.schema?.artifacts || []).find((item) => item.key === key) || null;
  }

  function renderSchema() {
    const artifacts = state.schema?.artifacts || [];
    const artifactSelect = $("acceptanceArtifactSelect");
    const gateSelect = $("acceptanceGateSelect");
    if (artifactSelect) {
      const previous = artifactSelect.value;
      artifactSelect.innerHTML = artifacts
        .map((item) => `<option value="${escapeHtml(item.key)}">${escapeHtml(item.filename)} · ${escapeHtml((item.owner_roles || []).join(" / "))}</option>`)
        .join("");
      if (artifacts.some((item) => item.key === previous)) artifactSelect.value = previous;
    }
    if (gateSelect) {
      const gates = Array.from(new Set(artifacts.flatMap((item) => item.gate_ids || []))).sort();
      const previous = gateSelect.value;
      gateSelect.innerHTML = gates.map((gate) => `<option value="${escapeHtml(gate)}">${escapeHtml(gate)}</option>`).join("");
      if (gates.includes(previous)) gateSelect.value = previous;
    }
  }

  function renderSummary() {
    const result = state.status;
    const target = $("acceptanceSummary");
    const pill = $("acceptanceOverallStatus");
    if (!result || !target) return;
    const counts = result.status_counts || {};
    const openCount = result.work_items?.open_item_count ?? 0;
    const coverage = result.gates?.["AC-M2-01"]?.metrics?.page_coverage;
    target.innerHTML = [
      ["总体结论", result.overall_status === "passed" ? "已通过" : "尚未通过"],
      ["通过门禁", String(counts.passed || 0)],
      ["未通过", String(counts.failed || 0)],
      ["未评测", String(counts.not_evaluated || 0)],
      ["开放工作项", String(openCount)],
      ["OCR 页核算", Number.isFinite(Number(coverage)) ? `${(Number(coverage) * 100).toFixed(2)}%` : "待提供"],
    ].map(([label, value]) => `
      <div class="acceptance-stat">
        <span>${escapeHtml(label)}</span>
        <strong>${escapeHtml(value)}</strong>
      </div>`).join("");
    if (pill) {
      pill.textContent = result.overall_status === "passed" ? "正式通过" : `${openCount} 项待完成`;
      pill.classList.toggle("is-success", result.overall_status === "passed");
      pill.classList.toggle("is-warning", result.overall_status !== "passed");
    }
  }

  function renderWorkItems() {
    const target = $("acceptanceWorkItems");
    if (!target) return;
    const items = state.status?.work_items?.items || [];
    if (!items.length) {
      target.innerHTML = '<div class="empty-state">所有正式验收门禁均已关闭。</div>';
      return;
    }
    target.innerHTML = items.map((item) => {
      const candidates = item.candidate_files || [];
      const candidateMeta = candidates.length
        ? `<div class="acceptance-work-meta acceptance-work-meta--candidate">
            <span>候选证据：待人工复核 · ${escapeHtml(candidates.join("；"))}</span>
            <button class="ghost-btn" type="button" data-load-acceptance-candidate="${escapeHtml(item.acceptance_id)}">载入候选</button>
          </div>`
        : "";
      return `
        <article class="acceptance-work-card">
          <div class="acceptance-work-card__head">
            <strong>${escapeHtml(item.acceptance_id)}</strong>
            <span class="pill">${escapeHtml(item.status)}</span>
          </div>
          <p>${escapeHtml(item.required_action)}</p>
          <div class="acceptance-work-meta"><span>责任：${escapeHtml((item.owner_roles || []).join(" / "))}</span></div>
          <div class="acceptance-work-meta"><span>应交：${escapeHtml((item.input_files || []).join("；"))}</span></div>
          ${candidateMeta}
          <details>
            <summary>当前指标</summary>
            <pre>${escapeHtml(JSON.stringify(item.current_metrics || {}, null, 2))}</pre>
          </details>
        </article>`;
    }).join("");
  }

  function renderArtifact() {
    const editor = $("acceptanceArtifactEditor");
    const hash = $("acceptanceArtifactHash");
    const note = $("acceptanceEditorNote");
    if (!editor || !state.artifact) return;
    editor.value = JSON.stringify(state.artifact.payload, null, 2);
    if (hash) hash.textContent = state.artifact.sha256 ? `SHA ${state.artifact.sha256.slice(0, 12)}…` : "新文件";
    if (note) {
      const spec = artifactSpec(state.artifact.key);
      note.textContent = `${state.artifact.filename} · ${state.artifact.format.toUpperCase()} · 责任角色：${(spec?.owner_roles || []).join(" / ") || "未配置"}`;
    }
  }

  async function loadSchema() {
    state.schema = await request("/api/delivery/acceptance/schema");
    renderSchema();
  }

  async function loadArtifact(key) {
    const artifactKey = key || $("acceptanceArtifactSelect")?.value;
    if (!artifactKey) return;
    state.artifact = await request(`/api/delivery/acceptance/artifacts/${encodeURIComponent(artifactKey)}`);
    renderArtifact();
  }

  async function loadCandidate(gateId, button) {
    const note = $("acceptanceEditorNote");
    setBusy(button, true, "载入中…");
    try {
      const candidate = await request(`/api/delivery/acceptance/candidates/${encodeURIComponent(gateId)}`);
      const select = $("acceptanceArtifactSelect");
      if (select) select.value = candidate.artifact_key;
      state.artifact = {
        key: candidate.artifact_key,
        filename: candidate.filename,
        format: candidate.format,
        exists: Boolean(candidate.formal_sha256),
        sha256: candidate.formal_sha256,
        payload: candidate.payload,
      };
      renderArtifact();
      if (note) note.textContent = `${candidate.warning} 来源：${(candidate.sources || []).map((item) => item.path).join("；")}`;
      $("acceptanceArtifactEditor")?.scrollIntoView({ behavior: "smooth", block: "center" });
    } catch (error) {
      if (note) note.textContent = `候选载入失败：${error.message}`;
    } finally {
      setBusy(button, false);
    }
  }

  async function refresh() {
    if (state.loading) return;
    state.loading = true;
    const button = $("btnAcceptanceRefresh");
    setBusy(button, true, "刷新中…");
    try {
      if (!state.schema) await loadSchema();
      state.status = await request("/api/delivery/acceptance/status");
      renderSummary();
      renderWorkItems();
      if (!state.artifact) await loadArtifact();
    } catch (error) {
      const target = $("acceptanceWorkItems");
      if (target) target.innerHTML = `<div class="empty-state">验收工作台需要由 PowerRAG 后端提供服务：${escapeHtml(error.message)}</div>`;
    } finally {
      state.loading = false;
      setBusy(button, false);
    }
  }

  function loadTemplate() {
    const key = $("acceptanceArtifactSelect")?.value;
    const spec = artifactSpec(key);
    if (!spec || !$("acceptanceArtifactEditor")) return;
    $("acceptanceArtifactEditor").value = JSON.stringify(spec.template, null, 2);
    const note = $("acceptanceEditorNote");
    if (note) note.textContent = "已载入模板，尚未保存；请填写真实证据，不要保留占位值。";
  }

  async function saveArtifact() {
    const key = $("acceptanceArtifactSelect")?.value;
    const editor = $("acceptanceArtifactEditor");
    const button = $("btnAcceptanceSaveArtifact");
    const note = $("acceptanceEditorNote");
    if (!key || !editor) return;
    let payload;
    try {
      payload = JSON.parse(editor.value);
    } catch (error) {
      if (note) note.textContent = `JSON 语法错误：${error.message}`;
      editor.focus();
      return;
    }
    setBusy(button, true, "保存中…");
    try {
      const response = await request(`/api/delivery/acceptance/artifacts/${encodeURIComponent(key)}`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          "Idempotency-Key": `acceptance:${key}:${state.artifact?.sha256 || "new"}`,
        },
        body: JSON.stringify({ payload, expected_sha256: state.artifact?.sha256 || null }),
      });
      state.status = response.status;
      await loadArtifact(key);
      renderSummary();
      renderWorkItems();
      if (note) note.textContent = "证据文件已保存并重新计算门禁；不完整记录会继续显示为未通过。";
    } catch (error) {
      if (error.status === 409) await loadArtifact(key);
      if (note) note.textContent = `保存失败：${error.message}${error.status === 409 ? "；已重新加载最新版本。" : ""}`;
    } finally {
      setBusy(button, false);
    }
  }

  async function uploadEvidence() {
    const gateId = $("acceptanceGateSelect")?.value;
    const input = $("acceptanceEvidenceFile");
    const result = $("acceptanceEvidenceResult");
    const button = $("btnAcceptanceUploadEvidence");
    const file = input?.files?.[0];
    if (!gateId || !file) {
      if (result) result.textContent = "请选择验收项和证据文件。";
      return;
    }
    const form = new FormData();
    form.set("gate_id", gateId);
    form.set("file", file, file.name);
    setBusy(button, true, "上传中…");
    try {
      const payload = await request("/api/delivery/acceptance/evidence", { method: "POST", body: form });
      if (result) {
        result.innerHTML = `
          <strong>evidence_ref</strong><code>${escapeHtml(payload.evidence_ref)}</code>
          <strong>SHA-256</strong><code>${escapeHtml(payload.sha256)}</code>
          <button class="ghost-btn" type="button" data-copy-evidence-ref="${escapeHtml(payload.evidence_ref)}">复制引用</button>`;
      }
      if (input) input.value = "";
    } catch (error) {
      if (result) result.textContent = `上传失败：${error.message}`;
    } finally {
      setBusy(button, false);
    }
  }

  async function buildPackage() {
    const button = $("btnAcceptanceBuild");
    setBusy(button, true, "生成中…");
    try {
      const payload = await request("/api/delivery/acceptance/build-package", {
        method: "POST",
        headers: { "Idempotency-Key": `acceptance-package:${Date.now()}` },
      });
      state.status = payload;
      renderSummary();
      renderWorkItems();
      await loadHandoff();
      const note = $("acceptanceEditorNote");
      if (note) note.textContent = `验收包已生成：${payload.package_dir}；结论 ${payload.overall_status}；人工交接包已同步刷新。`;
    } catch (error) {
      const note = $("acceptanceEditorNote");
      if (note) note.textContent = `验收包生成失败：${error.message}`;
    } finally {
      setBusy(button, false);
    }
  }

  function renderHandoff() {
    const preview = $("acceptanceHandoffPreview");
    const meta = $("acceptanceHandoffMeta");
    if (!preview || !state.handoff) return;
    preview.textContent = state.handoff.content || "";
    if (meta) meta.textContent = `${state.handoff.filename} · SHA ${String(state.handoff.sha256 || "").slice(0, 12)}…`;
  }

  async function loadHandoff(button) {
    setBusy(button, true, "载入中…");
    try {
      state.handoff = await request("/api/delivery/acceptance/handoff");
      renderHandoff();
    } catch (error) {
      const preview = $("acceptanceHandoffPreview");
      if (preview) preview.textContent = `交接包尚不可用：${error.message} 请先点击“生成验收包”。`;
    } finally {
      setBusy(button, false);
    }
  }

  async function copyHandoff() {
    const content = state.handoff?.content || $("acceptanceHandoffPreview")?.textContent || "";
    const meta = $("acceptanceHandoffMeta");
    if (!content) return;
    try {
      await navigator.clipboard.writeText(content);
      if (meta) meta.textContent = `${state.handoff?.filename || "human_review_handoff.md"} · 已复制`;
    } catch {
      if (meta) meta.textContent = "复制失败，请在预览区手动选择文本。";
    }
  }

  function downloadHandoff() {
    const anchor = document.createElement("a");
    anchor.href = state.handoff?.download_url || "/api/delivery/acceptance/package-files/human_review_handoff.md";
    anchor.download = "human_review_handoff.md";
    anchor.click();
  }

  function downloadQueue() {
    if (!state.status?.work_items) return;
    const blob = new Blob([JSON.stringify(state.status.work_items, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "powerrag-prd-acceptance-work-items.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function copyEvidenceRef(value) {
    try {
      await navigator.clipboard.writeText(value);
      const result = $("acceptanceEvidenceResult");
      if (result) result.dataset.copied = "true";
    } catch {
      const result = $("acceptanceEvidenceResult");
      if (result) result.textContent = `请手动复制：${value}`;
    }
  }

  function mount() {
    if (state.mounted) return;
    state.mounted = true;
    $("btnAcceptanceRefresh")?.addEventListener("click", refresh);
    $("btnAcceptanceBuild")?.addEventListener("click", buildPackage);
    $("btnAcceptanceDownloadQueue")?.addEventListener("click", downloadQueue);
    $("btnAcceptanceLoadHandoff")?.addEventListener("click", (event) => loadHandoff(event.currentTarget));
    $("btnAcceptanceCopyHandoff")?.addEventListener("click", copyHandoff);
    $("btnAcceptanceDownloadHandoff")?.addEventListener("click", downloadHandoff);
    $("btnAcceptanceUploadEvidence")?.addEventListener("click", uploadEvidence);
    $("btnAcceptanceLoadTemplate")?.addEventListener("click", loadTemplate);
    $("btnAcceptanceSaveArtifact")?.addEventListener("click", saveArtifact);
    $("acceptanceArtifactSelect")?.addEventListener("change", (event) => loadArtifact(event.target.value));
    $("acceptanceEvidenceResult")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-copy-evidence-ref]");
      if (button) copyEvidenceRef(button.dataset.copyEvidenceRef);
    });
    $("acceptanceWorkItems")?.addEventListener("click", (event) => {
      const button = event.target.closest("[data-load-acceptance-candidate]");
      if (button) loadCandidate(button.dataset.loadAcceptanceCandidate, button);
    });
  }

  global.addEventListener("DOMContentLoaded", mount, { once: true });
  global.addEventListener("powerrag:page-enter", (event) => {
    if (event.detail?.id === "acceptance") refresh();
  });

  global.PowerRAGAcceptancePage = Object.freeze({ refresh, loadArtifact });
})(globalThis);
