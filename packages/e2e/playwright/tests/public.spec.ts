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

let hostProc: ChildProcess | null = null;

test.beforeAll(async () => {
  hostProc = spawnDeskHost();
  await waitForHost();
});

test.afterAll(async () => {
  if (hostProc && !hostProc.killed) hostProc.kill("SIGTERM");
});

test("public example.com: observe returns url and targets or empty ok", async () => {
  const userDataDir = path.join(
    repoRoot,
    "packages/e2e/playwright/.pw-user-data-public",
  );
  const { context, serviceWorker } = await launchExtensionContext(userDataDir);
  try {
    await pointExtensionAtHost(serviceWorker);
    const page = await context.newPage();
    await page.goto("https://example.com");
    await page.waitForLoadState("domcontentloaded");

    const tabId = await chromeTabIdForUrl(serviceWorker, "https://example.com");
    const humanTabId = tabId + 10_000;
    const handoff = await fetch(`${hostBase()}/v1/handoff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: "https://example.com",
        title: "Example Domain",
        human_tab_id: humanTabId,
        window_id: 1,
      }),
    }).then((r) => r.json());
    expect(handoff.run_id).toBeTruthy();

    const observe = await postBrowserWait({
      run_id: handoff.run_id,
      op: "observe",
      human_tab_id: humanTabId,
      tab_id: tabId,
    });
    const result = observe.result as Record<string, unknown>;
    // Must not throw / crash; ok true with url, even if targets sparse
    expect(result.ok).toBe(true);
    expect(String(result.url || "")).toContain("example.com");
    expect(result.tab_id).toBe(tabId);
  } finally {
    await context.close();
  }
});
