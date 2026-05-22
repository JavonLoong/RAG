const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const htmlPath = path.join(root, "frontend_app", "current_console", "index.html");
const html = fs.readFileSync(htmlPath, "utf8");

function assert(condition, message) {
  if (!condition) {
    console.error(`FAIL: ${message}`);
    process.exitCode = 1;
  }
}

const runAskIndex = html.indexOf("async function runAsk()");
const ensureIndex = html.indexOf("async function ensureAskContext");
const ensureCallIndex = html.indexOf("await ensureAskContext(question)");
const buildCallIndex = html.indexOf("const messages = buildAskMessages(question)");

assert(ensureIndex > -1, "console should define ensureAskContext()");
assert(runAskIndex > -1, "console should define runAsk()");
assert(ensureCallIndex > runAskIndex, "runAsk() should call ensureAskContext(question)");
assert(buildCallIndex > ensureCallIndex, "runAsk() should retrieve context before building LLM messages");
assert(!html.includes("尝试给出通用建议"), "LLM fallback should not invite general model answers without evidence");
assert(!html.includes("????? chunk"), "RAG missing-evidence message should not be mojibake question marks");
assert(!html.includes("??? RAG"), "RAG auto-search status should not be mojibake question marks");
assert(!html.includes("????????????.md"), "public demo evidence filenames should not be mojibake question marks");
assert(html.includes("demo-gt07-fault-021"), "public demo should include GT-07 fault evidence");
assert(html.includes("rankPublicDemoResults"), "public demo should rank static evidence instead of returning fixed top rows");

if (!process.exitCode) {
  console.log("PASS: console RAG ask requires retrieved context before LLM call");
}
