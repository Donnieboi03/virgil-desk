import path from "node:path";
import type { ChildProcess } from "node:child_process";
import type { Server } from "node:http";

import { test, expect } from "@playwright/test";

import {
  chromeTabIdForUrl,
  fixtureUrl,
  hostBase,
  launchExtensionContext,
  pointExtensionAtHost,
  postBrowserWait,
  repoRoot,
  spawnDeskHost,
  startFixtureServer,
  waitForHost,
} from "./helpers.js";

let hostProc: ChildProcess | null = null;
let fixtureServer: Server | null = null;

test.beforeAll(async () => {
  fixtureServer = startFixtureServer();
  hostProc = spawnDeskHost();
  await waitForHost();
});

test.afterAll(async () => {
  if (hostProc && !hostProc.killed) hostProc.kill("SIGTERM");
  fixtureServer?.close();
});

test("form fixture: observe then fill by target_id", async () => {
  const userDataDir = path.join(
    repoRoot,
    "packages/e2e/playwright/.pw-user-data-form",
  );
  const { context, serviceWorker } = await launchExtensionContext(userDataDir);
  try {
    await pointExtensionAtHost(serviceWorker);

    const page = await context.newPage();
    await page.goto(fixtureUrl());
    await page.waitForSelector("#demo");

    const tabId = await chromeTabIdForUrl(serviceWorker, fixtureUrl());
    const humanTabId = tabId + 10_000;
    const handoff = await fetch(`${hostBase()}/v1/handoff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: fixtureUrl(),
        title: "Extension Eyes smoke",
        human_tab_id: humanTabId,
        window_id: 1,
      }),
    }).then((r) => r.json());
    expect(handoff.run_id).toBeTruthy();
    const runId = handoff.run_id as string;

    const observe = await postBrowserWait({
      run_id: runId,
      op: "observe",
      human_tab_id: humanTabId,
      tab_id: tabId,
    });
    const obsResult = observe.result as Record<string, unknown>;
    expect(obsResult.ok).toBe(true);
    expect(obsResult.tab_id).toBe(tabId);
    const targets = (obsResult.interact_targets as unknown[]) || [];
    expect(targets.length).toBeGreaterThan(0);

    const emailTarget = (
      targets as { id: number; label?: string; kind?: string }[]
    ).find(
      (t) =>
        (t.label || "").toLowerCase().includes("email") ||
        (t.kind || "").includes("input"),
    );
    expect(emailTarget, "expected an email/input target").toBeTruthy();

    const fill = await postBrowserWait({
      run_id: runId,
      op: "fill",
      human_tab_id: humanTabId,
      tab_id: tabId,
      params: { target_id: emailTarget!.id, value: "ada@example.com" },
    });
    const fillResult = fill.result as Record<string, unknown>;
    expect(fillResult.ok).toBe(true);
    expect(fillResult.tab_id).toBe(tabId);
  } finally {
    await context.close();
  }
});
