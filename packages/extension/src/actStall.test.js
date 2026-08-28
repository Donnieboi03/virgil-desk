import { describe, it, expect } from "vitest";
import { updateActStall, isFailedAct } from "./actStall.js";

describe("actStall", () => {
  it("detects used:none as failed", () => {
    expect(isFailedAct({ ok: true, act_resolved: { used: "none" } })).toBe(true);
  });

  it("stalls after N consecutive failures", () => {
    let map = new Map();
    let stalled = false;
    for (let i = 0; i < 3; i++) {
      const r = updateActStall(
        map,
        "run",
        2,
        { ok: false, error: "stale_observe: run observe first" },
        3,
      );
      map = r.next;
      stalled = r.stalled;
    }
    expect(stalled).toBe(true);
  });

  it("resets on successful target_id hit", () => {
    let map = new Map();
    let r = updateActStall(map, "run", 2, { ok: false, act_resolved: { used: "none" } }, 3);
    map = r.next;
    r = updateActStall(
      map,
      "run",
      2,
      { ok: true, act_resolved: { used: "target_id" } },
      3,
    );
    expect(r.count).toBe(0);
    expect(r.stalled).toBe(false);
  });
});
