import { spawn, type ChildProcess } from "node:child_process";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, chromium } from "@playwright/test";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "../../../..");
const extensionPath = path.join(repoRoot, "packages/extension/dist");
const hostPort = 8799;

let hostProc: ChildProcess | null = null;

test.beforeAll(async () => {
  hostProc = spawn(
    "python",
    ["-m", "desk_host"],
    {
      cwd: path.join(repoRoot, "packages/host"),
      env: {
        ...process.env,
        DESK_AGENT_BACKEND: "mock",
        DESK_PORT: String(hostPort),
        DESK_HOST: "127.0.0.1",
      },
      stdio: "ignore",
    },
  );
  const base = `http://127.0.0.1:${hostPort}`;
  for (let i = 0; i < 30; i++) {
    try {
      const res = await fetch(`${base}/v1/health`);
      if (res.ok) return;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("desk-host failed to start");
});

test.afterAll(async () => {
  if (hostProc && !hostProc.killed) {
    hostProc.kill("SIGTERM");
  }
});

test("extension loads and host handoff smoke", async () => {
  const userDataDir = path.join(repoRoot, "packages/e2e/playwright/.pw-user-data");
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
    ],
  });

  try {
    let [serviceWorker] = context.serviceWorkers();
    if (!serviceWorker) {
      serviceWorker = await context.waitForEvent("serviceworker", { timeout: 15_000 });
    }
    expect(serviceWorker.url()).toContain("chrome-extension://");

    const page = await context.newPage();
    await page.goto("https://example.com");

    const base = `http://127.0.0.1:${hostPort}`;
    const health = await fetch(`${base}/v1/health`).then((r) => r.json());
    expect(health.ok).toBe(true);

    const handoff = await fetch(`${base}/v1/handoff`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        url: "https://example.com",
        title: "Example",
        human_tab_id: 1,
        window_id: 1,
      }),
    }).then((r) => r.json());

    expect(handoff.run_id).toBeTruthy();
    expect(handoff.items?.length).toBeGreaterThan(0);
  } finally {
    await context.close();
  }
});
