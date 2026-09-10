import { describe, expect, it } from "vitest";
import {
  mapKey,
  storeTargetMap,
  getTargetMap,
  clearTargetMap,
  clearMapsForTab,
} from "./targetMap.js";

describe("targetMap", () => {
  it("stores and retrieves by run and tab", () => {
    storeTargetMap("desk_abc", 42, {
      interact_targets: [{ id: 1, ref: "t1" }],
      scroll_containers: [],
      url: "https://example.com",
    });
    const got = getTargetMap("desk_abc", 42);
    expect(got?.interact_targets).toHaveLength(1);
    expect(mapKey("desk_abc", 42)).toBe("desk_abc:42");
    clearTargetMap("desk_abc", 42);
    expect(getTargetMap("desk_abc", 42)).toBeUndefined();
  });

  it("clears all maps for a tab", () => {
    storeTargetMap("run1", 7, { interact_targets: [], scroll_containers: [], url: "" });
    storeTargetMap("run2", 7, { interact_targets: [], scroll_containers: [], url: "" });
    clearMapsForTab(7);
    expect(getTargetMap("run1", 7)).toBeUndefined();
    expect(getTargetMap("run2", 7)).toBeUndefined();
  });
});
