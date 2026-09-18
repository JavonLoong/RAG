(function registerPowerRAGDeliveryComponents(global) {
  "use strict";

  function status(value, escapeHtml) {
    const normalized = String(value || "unknown");
    return '<span class="delivery-status" data-status="' + escapeHtml(normalized) + '">' +
      escapeHtml(normalized) + "</span>";
  }

  function row(model, escapeHtml) {
    const item = model || {};
    return '<div class="delivery-row">' +
      '<div class="delivery-row-main">' +
        '<div class="delivery-row-title"><strong>' + escapeHtml(item.title || "") + "</strong>" +
          status(item.status, escapeHtml) + "</div>" +
        '<div class="delivery-row-meta">' + escapeHtml(item.meta || "") + "</div>" +
      "</div>" +
      '<div class="delivery-row-actions">' + (item.actions || "") + "</div>" +
    "</div>";
  }

  global.PowerRAGDeliveryComponents = Object.freeze({ status: status, row: row });
})(globalThis);
