import { describe, expect, it } from "vitest";
import {
  applyBoardPatch,
  childrenOf,
  chooseNavigationOp,
  openTabPlacement,
  policyBlock,
  selectBoardRoots,
  urlsMatchForPark,
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

describe("openTabPlacement", () => {
  it("defaults to agent", () => {
    expect(openTabPlacement({ op: "openTab" })).toBe("agent");
    expect(openTabPlacement({ op: "openTab", params: {} })).toBe("agent");
  });

  it("accepts human placement", () => {
    expect(
      openTabPlacement({ op: "openTab", params: { placement: "human" } }),
    ).toBe("human");
  });
});

describe("urlsMatchForPark", () => {
  it("matches same origin path query ignoring hash and trailing slash", () => {
    expect(
      urlsMatchForPark(
        "https://ex.com/path/?q=1#a",
        "https://ex.com/path?q=1",
      ),
    ).toBe(true);
    expect(urlsMatchForPark("https://ex.com/a", "https://ex.com/b")).toBe(false);
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

  it("clears board before add when clear op first", () => {
    const board = {
      you: [{ id: "old", column: "you", title: "Old" }],
      agent: [],
      waiting: [],
    };
    const item = { id: "n1", column: "agent", title: "New" };
    const out = applyBoardPatch(board, [{ op: "clear" }, { op: "add", item }]);
    expect(out.you).toHaveLength(0);
    expect(out.agent).toHaveLength(1);
  });

  it("keeps parent/child relationship helpers", () => {
    const board = { you: [], agent: [], waiting: [] };
    const parent = { id: "p1", column: "agent", title: "Parent" };
    const child = {
      id: "c1",
      column: "agent",
      title: "Child",
      parent_id: "p1",
      kind: "subtask",
    };
    const out = applyBoardPatch(board, [
      { op: "add", item: parent },
      { op: "add", item: child },
    ]);
    expect(selectBoardRoots(out.agent).map((i) => i.id)).toEqual(["p1"]);
    expect(childrenOf(out.agent, "p1").map((i) => i.id)).toEqual(["c1"]);
  });
});
