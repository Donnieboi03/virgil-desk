#!/usr/bin/env node
/** Validate JSON schemas exist (smoke). */
import { readdirSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const dir = join(dirname(fileURLToPath(import.meta.url)), "..", "packages", "protocol", "schemas");
const files = readdirSync(dir).filter((f) => f.endsWith(".json"));
if (!files.length) {
  console.error("No schema files found");
  process.exit(1);
}
console.log(`OK: ${files.length} schema files`);
process.exit(0);
