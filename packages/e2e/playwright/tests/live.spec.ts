import path from "node:path";
import type { ChildProcess } from "node:child_process";

import { test, expect } from "@playwright/test";

import {
  chromeTabIdForUrl,
  hostBase,
  launchExtensionContext,
  pointExtensionAtHost,
  postBrowserWait,
  repoRoot,
  spawnDeskHost,
  waitForHost,
} from "./helpers.js";

const live = process.env.DESK_E2E_LIVE === "1";

test.describe("live sites (opt-in)", () => {
  test.skip(!live, "Set DESK_E2E_LIVE=1 with a logged-in profile to run");

  let hostProc: ChildProcess | null = null;

  test.beforeAll(async () => {
    hostProc = spawnDeskHost();
    await waitForHost();
  });

  test.afterAll(async () => {
    if (hostProc && !hostProc.killed) hostProc.kill("SIGTERM");
  });

  test("gmail: observe without crash (no send)", async () => {
    const userDataDir = path.join(
      repoRoot,
      "packages/e2e/playwright/.pw-user-data-live",
    );
    const { context, serviceWorker } = await launchExtensionContext(userDataDir);
    try {
      await pointExtensionAtHost(serviceWorker);
      const page = await context.newPage();
      await page.goto("https://mail.google.com/", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(3000);

      const tabId = await chromeTabIdForUrl(serviceWorker, "https://mail.google.com");
      const humanTabId = tabId + 10_000;
      const handoff = await fetch(`${hostBase()}/v1/handoff`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: "https://mail.google.com/",
          title: "Gmail",
          human_tab_id: humanTabId,
          window_id: 1,
        }),
      }).then((r) => r.json());
      expect(handoff.run_id).toBeTruthy();

      const scrape = await postBrowserWait({
        run_id: handoff.run_id,
        op: "scrape",
        human_tab_id: humanTabId,
        tab_id: tabId,
      });
      const result = scrape.result as Record<string, unknown>;
      // Null-safe: must return a shaped result, never throw host 500
      expect(result).toBeTruthy();
      expect(result.tab_id).toBe(tabId);
      expect("ok" in result).toBe(true);
      expect("url" in result).toBe(true);
    } finally {
      await context.close();
    }
  });

  test("linkedin: null-safe scrape (expect soft-fail ok)", async () => {
    const userDataDir = path.join(
      repoRoot,
      "packages/e2e/playwright/.pw-user-data-live",
    );
    const { context, serviceWorker } = await launchExtensionContext(userDataDir);
    try {
      await pointExtensionAtHost(serviceWorker);
      const page = await context.newPage();
      await page.goto("https://www.linkedin.com/", {
        waitUntil: "domcontentloaded",
      });
      await page.waitForTimeout(2000);

      const tabId = await chromeTabIdForUrl(serviceWorker, "https://www.linkedin.com");
      const humanTabId = tabId + 10_000;
      const handoff = await fetch(`${hostBase()}/v1/handoff`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          url: "https://www.linkedin.com/",
          title: "LinkedIn",
          human_tab_id: humanTabId,
          window_id: 1,
        }),
      }).then((r) => r.json());

      const scrape = await postBrowserWait({
        run_id: handoff.run_id,
        op: "scrape",
        human_tab_id: humanTabId,
        tab_id: tabId,
      });
      const result = scrape.result as Record<string, unknown>;
      expect(result).toBeTruthy();
      expect("ok" in result).toBe(true);
      // url may be empty string after hostile inject — must not be missing
      expect(typeof result.url).toBe("string");
    } finally {
      await context.close();
    }
  });
});
