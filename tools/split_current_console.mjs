import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const root = resolve(import.meta.dirname, "..");
const indexPath = resolve(root, "frontend_app/current_console/index.html");
const cssPath = resolve(root, "frontend_app/current_console/styles/console.css");
const appPath = resolve(root, "frontend_app/current_console/modules/console-app.js");
const source = readFileSync(indexPath, "utf8");

const styleStart = source.indexOf("  <style>");
const styleEnd = source.indexOf("</style>", styleStart);
if (styleStart < 0 || styleEnd < 0) throw new Error("Inline console stylesheet was not found");
const css = source.slice(styleStart + "  <style>".length, styleEnd).replace(/^\s*@charset "UTF-8";\s*/u, "");

const scriptMarker = "  <script>\n\n// Configure pdf.js worker";
const scriptStart = source.indexOf(scriptMarker);
const scriptEnd = source.indexOf("\n\n</script>\n\n</head>", scriptStart);
if (scriptStart < 0 || scriptEnd < 0) throw new Error("Inline console application script was not found");
const app = source.slice(scriptStart + "  <script>".length, scriptEnd);

mkdirSync(dirname(cssPath), { recursive: true });
mkdirSync(dirname(appPath), { recursive: true });
writeFileSync(cssPath, `@charset "UTF-8";\n${css.trim()}\n`, "utf8");
writeFileSync(appPath, `${app.trim()}\n`, "utf8");

const withoutStyle = source.slice(0, styleStart)
  + '  <link rel="stylesheet" href="styles/console.css">\n'
  + source.slice(styleEnd + "</style>".length, scriptStart);
const rewritten = withoutStyle
  + '  <script src="modules/console-app.js" defer></script>'
  + source.slice(scriptEnd + "\n\n</script>".length);
writeFileSync(indexPath, rewritten, "utf8");

process.stdout.write(JSON.stringify({ indexPath, cssPath, appPath, cssBytes: css.length, appBytes: app.length }));
