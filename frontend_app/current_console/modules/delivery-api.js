(function registerPowerRAGDeliveryApi(global) {
  "use strict";

  function jsonOptions(method, payload, headers) {
    return {
      method: method,
      headers: Object.assign({ "Content-Type": "application/json" }, headers || {}),
      body: JSON.stringify(payload)
    };
  }

  function request(path, options, timeoutMs, dependencies) {
    const config = dependencies || {};
    if (typeof config.requestJson !== "function") {
      throw new Error("PowerRAG delivery API requires requestJson");
    }
    const headers = new Headers((options && options.headers) || {});
    headers.set("X-Project-ID", String(config.projectId || "default"));
    headers.set(
      "X-Correlation-ID",
      global.crypto && typeof global.crypto.randomUUID === "function"
        ? global.crypto.randomUUID()
        : "ui-" + Date.now()
    );
    return config.requestJson(
      path,
      Object.assign({}, options || {}, { headers: headers }),
      timeoutMs || 120000
    );
  }

  global.PowerRAGDeliveryApi = Object.freeze({ jsonOptions: jsonOptions, request: request });
})(globalThis);
