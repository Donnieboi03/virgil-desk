/** Build MV3 extension into dist/ */
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

const files = [
  "manifest.json",
  "background.js",
  "panel.html",
  "panel.css",
  "panel.js",
  "options.html",
  "options.js",
  "content-handoff.js",
];
for (const f of files) {
  cpSync(join(root, "src", f), join(dist, f));
}
console.log("Built extension → dist/");
