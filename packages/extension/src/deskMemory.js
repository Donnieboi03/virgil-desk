/**
 * Virgil Desk shared memory — notepad + last-N execute summaries + semantic facts.
 * SoT: chrome.storage.local keys virgil_desk_memory_v1 / virgil_desk_semantic_v1
 */

export const MEMORY_KEY = "virgil_desk_memory_v1";
export const SEMANTIC_KEY = "virgil_desk_semantic_v1";

export function emptyMemory() {
  return { global_recent: [], by_run_id: {} };
}

export function emptySemantic() {
  return { facts: [] };
}

export function appendRecent(memory, entry, recentMax = 3) {
  const out = {
    global_recent: [...(memory.global_recent || [])],
    by_run_id: { ...(memory.by_run_id || {}) },
  };
  out.global_recent.push(entry);
  if (recentMax > 0 && out.global_recent.length > recentMax) {
    out.global_recent = out.global_recent.slice(-recentMax);
  }
  return out;
}

export function seedRunNotepad(memory, runId, { decomposition = "", mission = "" } = {}) {
  const out = {
    global_recent: [...(memory.global_recent || [])],
    by_run_id: { ...(memory.by_run_id || {}) },
  };
  const existing = out.by_run_id[runId] || {};
  out.by_run_id[runId] = {
    decomposition: decomposition || existing.decomposition || "",
    mission: mission || existing.mission || "",
    bullets: [...(existing.bullets || [])],
  };
  return out;
}

export function appendNotepadBullet(
  memory,
  runId,
  bullet,
  { maxBullets = 20, maxChars = 4000 } = {},
) {
  const text = String(bullet || "").trim();
  if (!text) {
    return {
      global_recent: [...(memory.global_recent || [])],
      by_run_id: { ...(memory.by_run_id || {}) },
    };
  }
  const out = seedRunNotepad(memory, runId);
  const note = out.by_run_id[runId];
  let bullets = [...(note.bullets || []), text];
  if (maxBullets > 0 && bullets.length > maxBullets) {
    bullets = bullets.slice(-maxBullets);
  }
  while (maxChars > 0 && bullets.length && bullets.reduce((n, b) => n + b.length, 0) > maxChars) {
    bullets.shift();
  }
  note.bullets = bullets;
  return out;
}

export function applyMemoryPatch(
  memory,
  ops,
  { recentMax = 3, maxBullets = 20, maxChars = 4000 } = {},
) {
  let out = {
    global_recent: [...(memory.global_recent || [])],
    by_run_id: { ...(memory.by_run_id || {}) },
  };
  for (const op of ops || []) {
    if (op.op === "seed_run") {
      out = seedRunNotepad(out, op.run_id || "", {
        decomposition: op.decomposition || "",
        mission: op.mission || "",
      });
    } else if (op.op === "append_recent") {
      if (op.entry && typeof op.entry === "object") {
        out = appendRecent(out, op.entry, recentMax);
      }
    } else if (op.op === "append_bullet") {
      out = appendNotepadBullet(out, op.run_id || "", op.bullet || "", {
        maxBullets,
        maxChars,
      });
    }
  }
  return out;
}

function isoNow() {
  return new Date().toISOString().replace(/\.\d{3}Z$/, "Z");
}

function newFactId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return crypto.randomUUID().replace(/-/g, "");
  }
  return `${Date.now().toString(16)}${Math.random().toString(16).slice(2, 10)}`;
}

export function upsertFact(
  semantic,
  {
    key,
    value,
    tags = [],
    source = "host",
    maxFacts = 20,
    maxKeyChars = 64,
    maxValueChars = 200,
  } = {},
) {
  const k = String(key || "")
    .trim()
    .slice(0, Math.max(0, maxKeyChars));
  const v = String(value || "")
    .trim()
    .slice(0, Math.max(0, maxValueChars));
  if (!k || !v) {
    return { facts: [...((semantic && semantic.facts) || [])] };
  }
  const tagList = (Array.isArray(tags) ? tags : [])
    .map((t) => String(t).trim())
    .filter(Boolean);
  let facts = [...((semantic && semantic.facts) || [])];
  const now = isoNow();
  let found = false;
  facts = facts.map((fact) => {
    if (!fact || typeof fact !== "object") return fact;
    if (String(fact.key || "") !== k) return fact;
    found = true;
    return {
      ...fact,
      key: k,
      value: v,
      tags: tagList,
      source: source || fact.source || "host",
      updated_at: now,
      id: fact.id || newFactId(),
    };
  });
  if (!found) {
    facts.push({
      id: newFactId(),
      key: k,
      value: v,
      tags: tagList,
      source: source || "host",
      updated_at: now,
    });
  }
  if (maxFacts > 0 && facts.length > maxFacts) {
    facts = [...facts]
      .sort((a, b) => String(a?.updated_at || "").localeCompare(String(b?.updated_at || "")))
      .slice(-maxFacts);
  }
  return { facts };
}

export function deleteFact(semantic, { key = "", id = "", factId = "" } = {}) {
  const facts = [...((semantic && semantic.facts) || [])];
  const k = String(key || "").trim();
  const fid = String(id || factId || "").trim();
  if (!k && !fid) return { facts };
  return {
    facts: facts.filter((fact) => {
      if (!fact || typeof fact !== "object") return false;
      if (k && String(fact.key || "") === k) return false;
      if (fid && String(fact.id || "") === fid) return false;
      return true;
    }),
  };
}

export function applySemanticPatch(
  semantic,
  ops,
  { maxFacts = 20, maxKeyChars = 64, maxValueChars = 200 } = {},
) {
  let out = { facts: [...((semantic && semantic.facts) || [])] };
  for (const op of ops || []) {
    if (op.op === "upsert_fact") {
      out = upsertFact(out, {
        key: op.key || "",
        value: op.value || "",
        tags: op.tags,
        source: op.source || "host",
        maxFacts,
        maxKeyChars,
        maxValueChars,
      });
    } else if (op.op === "delete_fact") {
      out = deleteFact(out, { key: op.key || "", id: op.id || op.fact_id || "" });
    }
  }
  return out;
}

export function formatSemanticForExecute(
  semantic,
  { packetMaxFacts = 10, maxKeyChars = 64, maxValueChars = 200 } = {},
) {
  let facts = [...((semantic && semantic.facts) || [])].filter(
    (f) => f && typeof f === "object",
  );
  facts.sort((a, b) => String(b.updated_at || "").localeCompare(String(a.updated_at || "")));
  if (packetMaxFacts > 0) facts = facts.slice(0, packetMaxFacts);
  return facts.map((fact) => ({
    key: String(fact.key || "").slice(0, Math.max(0, maxKeyChars)),
    value: String(fact.value || "").slice(0, Math.max(0, maxValueChars)),
    tags: [...(fact.tags || [])],
  }));
}

export function formatForExecute(
  memory,
  runId,
  {
    decomposition = "",
    semantic = null,
    packetMaxFacts = 10,
    maxKeyChars = 64,
    maxValueChars = 200,
  } = {},
) {
  const note = (memory.by_run_id || {})[runId] || {};
  const decomp = decomposition || note.decomposition || "";
  return {
    recent_executions: [...(memory.global_recent || [])],
    run_notepad: {
      decomposition: decomp,
      mission: note.mission || "",
      bullets: [...(note.bullets || [])],
    },
    semantic_facts: formatSemanticForExecute(semantic || emptySemantic(), {
      packetMaxFacts,
      maxKeyChars,
      maxValueChars,
    }),
  };
}

/** Split memory_patch ops into working/episodic vs semantic. */
export function partitionMemoryOps(ops) {
  const memoryOps = [];
  const semanticOps = [];
  for (const op of ops || []) {
    if (!op || typeof op !== "object") continue;
    if (op.op === "upsert_fact" || op.op === "delete_fact") semanticOps.push(op);
    else memoryOps.push(op);
  }
  return { memoryOps, semanticOps };
}
