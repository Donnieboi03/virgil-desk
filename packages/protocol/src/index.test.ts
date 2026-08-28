import { describe, expect, it } from "vitest";
import {
  applyBoardPatch,
  emptyBoard,
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
