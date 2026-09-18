(function registerPowerRAGDeliveryState(global) {
  "use strict";

  function create() {
    return {
      projects: [],
      projectId: "default",
      identity: null,
      health: null,
      providers: [],
      tasks: [],
      documents: [],
      reviewQueue: [],
      graphs: [],
      fmeaTemplates: [],
      fmeaTasks: [],
      selectedDocumentVersions: new Set(),
      selectedReviewDocumentIds: new Set(),
      selectedTaskIds: new Set(),
      activeGraphVersionId: "",
      loading: false,
      lastError: ""
    };
  }

  function retainVisible(selection, visibleIds) {
    const visible = visibleIds instanceof Set ? visibleIds : new Set(visibleIds || []);
    return new Set(Array.from(selection || []).filter(function keep(id) { return visible.has(id); }));
  }

  global.PowerRAGDeliveryState = Object.freeze({ create: create, retainVisible: retainVisible });
})(globalThis);
