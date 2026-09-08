import { describe, expect, it } from "vitest";
import {
  applyBoardPatch,
  childrenOf,
  emptyBoard,
  selectBoardRoots,
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

  it("adds child with parent_id", () => {
    const parent: WorkItem = {
      id: "p1",
      column: "agent",
      title: "Parent",
      source: { kind: "handoff" },
      status: "running",
      kind: "parent",
    };
    const child: WorkItem = {
      id: "p1_sub_1",
      column: "agent",
      title: "Child",
      source: { kind: "handoff" },
      status: "proposed",
      kind: "subtask",
      parent_id: "p1",
    };
    const next = applyBoardPatch(emptyBoard(), [
      { op: "add", item: parent },
      { op: "add", item: child },
    ]);
    expect(selectBoardRoots(next.agent).map((i) => i.id)).toEqual(["p1"]);
    expect(childrenOf(next.agent, "p1").map((i) => i.id)).toEqual(["p1_sub_1"]);
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
