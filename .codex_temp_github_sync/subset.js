
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