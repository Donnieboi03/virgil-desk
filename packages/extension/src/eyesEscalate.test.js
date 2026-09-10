import { describe, it, expect } from "vitest";
import {
  promoteEyesExcerpt,
  excerptFromPageTree,
  urlPathHint,
} from "./eyesEscalate.js";

describe("promoteEyesExcerpt", () => {
  it("prefers deep text when long enough", () => {
    const deep = "Application verified link has expired. Please request a new one.";
    const out = promoteEyesExcerpt(deep, 'Page: X\n[status "ignored"]', {
      minChars: 40,
      maxChars: 4000,
    });
    expect(out).toBe(deep);
  });

  it("falls back to page_tree labels when deep text is thin", () => {
    const tree = [
      "Page: Job",
      "URL: https://example.com/expired",
      "",
      '[status "This invitation has expired"]',
      '[heading level=1 "Verified expired"]',
    ].join("\n");
    const out = promoteEyesExcerpt("hi", tree, { minChars: 40, maxChars: 4000 });
    expect(out).toContain("This invitation has expired");
    expect(out).toContain("Verified expired");
    expect(out).not.toMatch(/^Page:/m);
  });

  it("returns null when both channels are thin", () => {
    expect(promoteEyesExcerpt("", "Page: X\nURL: y", { minChars: 40 })).toBeNull();
    expect(promoteEyesExcerpt("short", null, { minChars: 40 })).toBeNull();
  });

  it("combines thin deep + thin tree when together enough", () => {
    const deep = "Status: invitation expired."; // < 40
    const tree = '[alert "Please contact support for a new link."]';
    const out = promoteEyesExcerpt(deep, tree, { minChars: 40 });
    expect(out).toContain("invitation expired");
    expect(out).toContain("contact support");
  });
});

describe("excerptFromPageTree", () => {
  it("skips headers and bare role lines", () => {
    const tree = [
      "Page: T",
      "URL: https://x",
      "[main]",
      '[button "Continue"]',
      "Visible body line here",
    ].join("\n");
    const out = excerptFromPageTree(tree);
    expect(out).toContain("Continue");
    expect(out).toContain("Visible body line here");
    expect(out).not.toContain("[main]");
  });
});

describe("urlPathHint", () => {
  it("detects expired / login / not_found from path and title", () => {
    expect(urlPathHint("https://jobs.example.com/verified-expired", "")).toBe(
      "expired_or_stale",
    );
    expect(urlPathHint("https://app.example.com/login", "Sign in")).toBe(
      "login_or_auth",
    );
    expect(urlPathHint("https://x.com/404", "Not Found")).toBe("not_found");
  });

  it("returns null when nothing matches", () => {
    expect(urlPathHint("https://mail.example.com/inbox", "Inbox")).toBeNull();
    expect(urlPathHint(null, null)).toBeNull();
  });
});
