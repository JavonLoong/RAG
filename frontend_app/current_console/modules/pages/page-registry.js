(function registerPageRegistry(global) {
  "use strict";

  const pages = new Map();

  function register(definition) {
    const page = Object.freeze({
      id: String(definition.id || "").trim(),
      mode: definition.mode === "graphrag" ? "graphrag" : "rag",
      title: String(definition.title || "").trim(),
    });
    if (!page.id) throw new Error("PowerRAG page modules require an id");
    pages.set(page.id, page);
    return page;
  }

  function normalize(value, fallback = "overview") {
    const id = String(value || "").replace(/^#/, "");
    return pages.has(id) ? id : fallback;
  }

  function idsForMode(mode) {
    const normalizedMode = mode === "graphrag" ? "graphrag" : "rag";
    return Array.from(pages.values())
      .filter((page) => page.mode === normalizedMode)
      .map((page) => page.id);
  }

  function enter(id) {
    const page = pages.get(normalize(id));
    global.dispatchEvent(new CustomEvent("powerrag:page-enter", { detail: page }));
    return page;
  }

  global.PowerRAGPages = Object.freeze({ register, normalize, idsForMode, enter });
})(globalThis);
