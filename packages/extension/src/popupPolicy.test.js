import { describe, it, expect } from "vitest";
import { shouldCloseSpawnedTab } from "./popupPolicy.js";

describe("shouldCloseSpawnedTab", () => {
  it("keeps same-origin Gmail navigations", () => {
    expect(
      shouldCloseSpawnedTab(
        "https://mail.google.com/mail/u/0/#inbox",
        "https://mail.google.com/mail/u/0/#inbox/abc",
      ),
    ).toBe(false);
  });

  it("closes LinkedIn opened from Gmail", () => {
    expect(
      shouldCloseSpawnedTab(
        "https://mail.google.com/mail/u/0/#inbox",
        "https://www.linkedin.com/news/story/1",
      ),
    ).toBe(true);
  });

  it("ignores about:blank until real URL", () => {
    expect(
      shouldCloseSpawnedTab("https://mail.google.com/", "about:blank"),
    ).toBe(false);
  });
});
