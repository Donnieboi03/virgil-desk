import { describe, it, expect } from "vitest";
import {
  humanAttentionSummary,
  shouldNotifyAttention,
  youNeedsHuman,
} from "./boardNotify.js";

describe("boardNotify", () => {
  it("counts awaiting_human, remainders, and You proposals — not routine proposed", () => {
    const s = humanAttentionSummary({
      you: [
        { id: "y1", status: "awaiting_human", title: "Auth" },
        { id: "y2", status: "proposed", title: "Homework" },
        { id: "y3", status: "proposed", park_kind: "human_remainder", title: "Decide" },
        {
          id: "y4",
          status: "proposed",
          title: "Slot",
          proposals: [{ id: "p1", kind: "calendar_slot" }],
        },
        { id: "y5", status: "done", title: "Done" },
      ],
      waiting: [],
      agent: [],
    });
    expect(s.youNeeds).toBe(3);
    expect(s.waitingNeeds).toBe(0);
    expect(s.total).toBe(3);
  });

  it("folds leftover waiting[] into attention until migrate clears it", () => {
    const s = humanAttentionSummary({
      you: [],
      waiting: [
        {
          id: "w1",
          status: "proposed",
          title: "Legacy slot",
          proposals: [{ id: "p1", kind: "calendar_slot" }],
        },
      ],
    });
    expect(s.total).toBe(1);
  });

  it("does not treat plain You proposed as needing ping", () => {
    expect(youNeedsHuman({ status: "proposed", title: "Review" })).toBe(false);
    expect(
      humanAttentionSummary({
        you: [{ id: "y1", status: "proposed", title: "Review" }],
        waiting: [],
      }).total,
    ).toBe(0);
  });

  it("notifies only when attention increases", () => {
    const a = humanAttentionSummary({ you: [], waiting: [] });
    const b = humanAttentionSummary({
      you: [{ id: "y1", status: "awaiting_human", title: "Gate" }],
      waiting: [],
    });
    expect(shouldNotifyAttention(a, b)).toBe(true);
    expect(shouldNotifyAttention(b, b)).toBe(false);
  });
});
