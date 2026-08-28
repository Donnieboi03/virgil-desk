import { describe, expect, it } from "vitest";
import { resolveTarget } from "./interactBundle.js";

describe("resolveTarget target_id coercion", () => {
  it("matches string target_id to numeric id", () => {
    const targets = [
      { id: 7, ref: "t7", kind: "clickable", label: "Apply" },
      { id: 1, ref: "s1", kind: "scroll_container" },
    ];
    const resolved = resolveTarget(targets, { target_id: "7" });
    expect(resolved.used).toBe("target_id");
    expect(resolved.target?.ref).toBe("t7");
  });

  it("prefers scroll container ref s-prefix over interact id collision", () => {
    const scrollTargets = [{ id: 1, ref: "s1", kind: "scroll_container" }];
    const byRef = resolveTarget(scrollTargets, { ref: "s1" });
    expect(byRef.target?.kind).toBe("scroll_container");
  });
});
