import { describe, it, expect } from "vitest";
import {
  emptyMemory,
  emptySemantic,
  appendRecent,
  seedRunNotepad,
  appendNotepadBullet,
  applyMemoryPatch,
  applySemanticPatch,
  upsertFact,
  deleteFact,
  formatForExecute,
  formatSemanticForExecute,
  partitionMemoryOps,
} from "./deskMemory.js";

describe("deskMemory", () => {
  it("keeps only last N recent entries", () => {
    let mem = emptyMemory();
    mem = appendRecent(mem, { item_id: "a", summary: "one" }, 3);
    mem = appendRecent(mem, { item_id: "b", summary: "two" }, 3);
    mem = appendRecent(mem, { item_id: "c", summary: "three" }, 3);
    mem = appendRecent(mem, { item_id: "d", summary: "four" }, 3);
    expect(mem.global_recent.map((e) => e.item_id)).toEqual(["b", "c", "d"]);
  });

  it("seeds and appends notepad bullets with char trim", () => {
    let mem = seedRunNotepad(emptyMemory(), "run1", {
      decomposition: "triage inbox",
    });
    mem = appendNotepadBullet(mem, "run1", "opened GitHub thread", {
      maxBullets: 10,
      maxChars: 30,
    });
    mem = appendNotepadBullet(mem, "run1", "failed search", {
      maxBullets: 10,
      maxChars: 30,
    });
    expect(mem.by_run_id.run1.decomposition).toBe("triage inbox");
    expect(mem.by_run_id.run1.bullets.length).toBeGreaterThanOrEqual(1);
    expect(mem.by_run_id.run1.bullets.join("").length).toBeLessThanOrEqual(30);
  });

  it("applyMemoryPatch handles seed + recent + bullet", () => {
    const mem = applyMemoryPatch(emptyMemory(), [
      { op: "seed_run", run_id: "r1", decomposition: "split work" },
      {
        op: "append_recent",
        entry: { item_id: "i1", title: "t", outcome: "done", summary: "ok" },
      },
      { op: "append_bullet", run_id: "r1", bullet: "note A" },
    ]);
    expect(mem.by_run_id.r1.decomposition).toBe("split work");
    expect(mem.global_recent).toHaveLength(1);
    expect(mem.by_run_id.r1.bullets).toEqual(["note A"]);
  });

  it("formatForExecute slices fields for prompt", () => {
    const mem = applyMemoryPatch(emptyMemory(), [
      { op: "seed_run", run_id: "r1", decomposition: "d1", mission: "m1" },
      { op: "append_bullet", run_id: "r1", bullet: "b1" },
      {
        op: "append_recent",
        entry: { item_id: "x", summary: "prior" },
      },
    ]);
    const fmt = formatForExecute(mem, "r1");
    expect(fmt.decomposition).toBeUndefined();
    expect(fmt.run_notepad.decomposition).toBe("d1");
    expect(fmt.run_notepad.bullets).toEqual(["b1"]);
    expect(fmt.recent_executions[0].summary).toBe("prior");
    expect(fmt.semantic_facts).toEqual([]);
  });

  it("upsertFact supersedes by key and respects caps", () => {
    let sem = emptySemantic();
    sem = upsertFact(sem, {
      key: "prefer_concise",
      value: "short",
      tags: ["user"],
      source: "manual",
    });
    sem = upsertFact(sem, {
      key: "prefer_concise",
      value: "shorter",
      tags: ["user"],
      source: "host",
    });
    expect(sem.facts).toHaveLength(1);
    expect(sem.facts[0].value).toBe("shorter");
    for (let i = 0; i < 5; i++) {
      sem = upsertFact(sem, {
        key: `k${i}`,
        value: `v${i}`,
        tags: ["decision"],
        maxFacts: 3,
      });
    }
    expect(sem.facts.length).toBe(3);
    sem = deleteFact(sem, { key: sem.facts[0].key });
    expect(sem.facts.length).toBe(2);
  });

  it("applySemanticPatch and formatSemanticForExecute", () => {
    const sem = applySemanticPatch(emptySemantic(), [
      {
        op: "upsert_fact",
        key: "yc_no_false_close",
        value: "Do not single-closure YC review",
        tags: ["decision"],
      },
      { op: "upsert_fact", key: "tone", value: "concise", tags: ["user"] },
    ]);
    const facts = formatSemanticForExecute(sem, { packetMaxFacts: 1 });
    expect(facts).toHaveLength(1);
    expect(facts[0].key).toBeTruthy();
    const fmt = formatForExecute(emptyMemory(), "r1", { semantic: sem });
    expect(fmt.semantic_facts.length).toBe(2);
  });

  it("partitionMemoryOps splits semantic vs working", () => {
    const { memoryOps, semanticOps } = partitionMemoryOps([
      { op: "seed_run", run_id: "r" },
      { op: "upsert_fact", key: "a", value: "b" },
      { op: "append_bullet", run_id: "r", bullet: "x" },
      { op: "delete_fact", key: "a" },
    ]);
    expect(memoryOps.map((o) => o.op)).toEqual(["seed_run", "append_bullet"]);
    expect(semanticOps.map((o) => o.op)).toEqual(["upsert_fact", "delete_fact"]);
  });
});
