/**
 * Virgil Desk shared memory — notepad + last-N execute summaries.
 * SoT: chrome.storage.local key virgil_desk_memory_v1
 */

export const MEMORY_KEY = "virgil_desk_memory_v1";

export function emptyMemory() {
  return { global_recent: [], by_run_id: {} };
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

export function formatForExecute(memory, runId, { decomposition = "" } = {}) {
  const note = (memory.by_run_id || {})[runId] || {};
  const decomp = decomposition || note.decomposition || "";
  return {
    recent_executions: [...(memory.global_recent || [])],
    run_notepad: {
      decomposition: decomp,
      mission: note.mission || "",
      bullets: [...(note.bullets || [])],
    },
    decomposition: decomp,
  };
}
