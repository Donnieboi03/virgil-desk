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
  // Bump dir name when extension SW surface changes (upload/notify) so Playwright
  // does not reuse a stale cached service worker.
  const userDataDir = path.join(
    repoRoot,
    "packages/e2e/playwright/.pw-user-data-form-v2",
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

    const goBtn = (
      targets as { id: number; kind?: string; label?: string }[]
    ).find(
      (t) =>
        (t.label || "").toLowerCase().includes("submit") ||
        (t.label || "").toLowerCase() === "go",
    );
    expect(goBtn, "expected Submit/Go clickable").toBeTruthy();
    const click = await postBrowserWait({
      run_id: runId,
      op: "click",
      human_tab_id: humanTabId,
      tab_id: tabId,
      params: { target_id: goBtn!.id },
    });
    expect((click.result as { ok?: boolean }).ok).toBe(true);

    const probe = await postBrowserWait({
      run_id: runId,
      op: "probe_form",
      human_tab_id: humanTabId,
      tab_id: tabId,
    });
    expect((probe.result as { ok?: boolean }).ok).toBe(true);

    const vaultId = await serviceWorker.evaluate(async () => {
      const key = "virgil_desk_vault_v1";
      const id = "vault_pw_feas";
      await chrome.storage.local.set({
        [key]: {
          files: [
            {
              id,
              name: "resume.pdf",
              mime: "application/pdf",
              base64: btoa("%PDF-1.4 feasibility"),
              added_at: new Date().toISOString(),
            },
          ],
        },
      });
      return id;
    });

    const observe2 = await postBrowserWait({
      run_id: runId,
      op: "observe",
      human_tab_id: humanTabId,
      tab_id: tabId,
    });
    const targets2 =
      ((observe2.result as { interact_targets?: { id: number; kind?: string }[] })
        .interact_targets) || [];
    const fileTarget = targets2.find((t) => t.kind === "file");
    expect(fileTarget, "expected kind:file resume input").toBeTruthy();

    const upload = await postBrowserWait({
      run_id: runId,
      op: "upload",
      human_tab_id: humanTabId,
      tab_id: tabId,
      params: { target_id: fileTarget!.id, vault_id: vaultId },
    });
    const upResult = upload.result as { ok?: boolean; error?: string; act_resolved?: unknown };
    expect(upResult.ok, upResult.error || "upload failed").toBe(true);
    expect(upResult.act_resolved, "upload should return act_resolved").toBeTruthy();

    const emptyUpload = await postBrowserWait({
      run_id: runId,
      op: "upload",
      human_tab_id: humanTabId,
      tab_id: tabId,
      params: { target_id: fileTarget!.id, vault_id: "vault_missing" },
    });
    const miss = emptyUpload.result as { ok?: boolean; error?: string };
    expect(miss.ok).toBe(false);
    expect(String(miss.error || "")).toMatch(/vault file not found/i);
  } finally {
    await context.close();
  }
});
