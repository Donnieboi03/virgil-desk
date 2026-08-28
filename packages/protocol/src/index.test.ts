import { describe, expect, it } from "vitest";
import {
  applyBoardPatch,
  emptyBoard,
  type InteractTarget,
  type WorkItem,
} from "./index.js";

describe("applyBoardPatch", () => {
  it("adds item to column", () => {
    const item: WorkItem = {
      id: "w1",
      column: "agent",
      title: "Research",
      source: { kind: "handoff", url: "https://example.com" },
      status: "proposed",
    };
    const next = applyBoardPatch(emptyBoard(), [{ op: "add", item }]);
    expect(next.agent).toHaveLength(1);
    expect(next.agent[0].id).toBe("w1");
  });
});

describe("interact target shape", () => {
  it("accepts observe payload fields", () => {
    const target: InteractTarget = {
      id: 7,
      ref: "t7",
      kind: "clickable",
      label: "Inbox row",
      rect: { x: 0, y: 0, w: 100, h: 36 },
      center: { x: 50, y: 18 },
    };
    expect(target.ref).toBe("t7");
  });
});
