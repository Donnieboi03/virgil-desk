import { describe, expect, it } from "vitest";
import {
  applyBoardPatch,
  chooseNavigationOp,
  policyBlock,
} from "./tabPolicy.js";

describe("chooseNavigationOp", () => {
  it("duplicates when same origin and path", () => {
    expect(
      chooseNavigationOp(
        "https://example.com/job/1?q=a",
        "https://example.com/job/1#section",
      ),
    ).toBe("duplicateTab");
  });

  it("opens new tab for different URL", () => {
    expect(
      chooseNavigationOp("https://example.com/job/1", "https://other.com/x"),
    ).toBe("openTab");
  });
});

describe("policyBlock", () => {
  it("blocks agent ops on human tab", () => {
    expect(policyBlock({ op: "click", human_tab_id: 3 }, 3)).toBe(
      "human_tab_blocked",
    );
  });

  it("allows snapshot on human tab", () => {
    expect(
      policyBlock({ op: "captureHandoffSnapshot", human_tab_id: 3 }, 3),
    ).toBeNull();
  });
});

describe("applyBoardPatch", () => {
  it("merges add ops into columns", () => {
    const board = { you: [], agent: [], waiting: [] };
    const item = { id: "a1", column: "agent", title: "Research" };
    const out = applyBoardPatch(board, [{ op: "add", item }]);
    expect(out.agent).toHaveLength(1);
    expect(out.agent[0].id).toBe("a1");
  });
});
