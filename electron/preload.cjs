const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("powerRagDesktop", {
  platform: process.platform,
  version: process.versions.electron,
  pickPowerRagCorpus: (options = {}) => ipcRenderer.invoke("power-rag:pick-power-rag-corpus", options),
});
