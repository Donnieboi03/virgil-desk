/** Build MV3 extension into dist/ */
import { cpSync, mkdirSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import * as esbuild from "esbuild";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const dist = join(root, "dist");
rmSync(dist, { recursive: true, force: true });
mkdirSync(dist, { recursive: true });

await esbuild.build({
  entryPoints: [join(root, "src/observe/interactBundle.js")],
  outfile: join(dist, "interactObserve.bundle.js"),
  bundle: true,
  format: "iife",
  globalName: "DeskInteract",
  platform: "browser",
  target: ["chrome109"],
  minify: false,
  sourcemap: false,
});

const files = [
  "manifest.json",
  "tabPolicy.js",
  "background.js",
  "targetMap.js",
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
console.log("Built extension → dist/ (with interactObserve.bundle.js)");
