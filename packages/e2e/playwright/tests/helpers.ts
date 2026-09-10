import { spawn, type ChildProcess } from "node:child_process";
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium, type BrowserContext, type Worker } from "@playwright/test";

declare const chrome: {
  storage: { sync: { set: (v: Record<string, string>) => Promise<void> } };
  tabs: {
    query: (q: Record<string, unknown>) => Promise<{ id?: number; url?: string }[]>;
  };
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));
export const repoRoot = path.resolve(__dirname, "../../../..");
export const extensionPath = path.join(repoRoot, "packages/extension/dist");
export const hostPort = 8799;
export const fixturePort = 8765;

export function hostBase(): string {
  return `http://127.0.0.1:${hostPort}`;
}

export async function waitForHost(base = hostBase(), attempts = 40): Promise<void> {
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${base}/v1/health`);
      if (res.ok) return;
    } catch {
      /* retry */
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("desk-host failed to start");
}

export function spawnDeskHost(): ChildProcess {
  return spawn("python", ["-m", "desk_host"], {
    cwd: path.join(repoRoot, "packages/host"),
    env: {
      ...process.env,
      DESK_AGENT_BACKEND: "mock",
      DESK_PORT: String(hostPort),
      DESK_HOST: "127.0.0.1",
    },
    stdio: "ignore",
  });
}

/** Serve tests/manual/path_b_smoke.html for form Eyes/Hands. */
export function startFixtureServer(): http.Server {
  const htmlPath = path.join(repoRoot, "tests/manual/path_b_smoke.html");
  const html = fs.readFileSync(htmlPath);
  const server = http.createServer((_req, res) => {
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
    res.end(html);
  });
  server.listen(fixturePort, "127.0.0.1");
  return server;
}

export function fixtureUrl(): string {
  return `http://127.0.0.1:${fixturePort}/`;
}

export async function launchExtensionContext(
  userDataDir: string,
): Promise<{ context: BrowserContext; serviceWorker: Worker }> {
  const context = await chromium.launchPersistentContext(userDataDir, {
    headless: false,
    args: [
      `--disable-extensions-except=${extensionPath}`,
      `--load-extension=${extensionPath}`,
    ],
  });
  let [serviceWorker] = context.serviceWorkers();
  if (!serviceWorker) {
    serviceWorker = await context.waitForEvent("serviceworker", { timeout: 15_000 });
  }
  return { context, serviceWorker };
}

export async function pointExtensionAtHost(
  serviceWorker: Worker,
  base = hostBase(),
): Promise<void> {
  await serviceWorker.evaluate(async (url) => {
    await chrome.storage.sync.set({ hostUrl: url });
  }, base);
  for (let i = 0; i < 40; i++) {
    const health = await fetch(`${base}/v1/health`).then((r) => r.json());
    if (health.extension_connected) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error("extension did not connect to desk-host");
}

export async function chromeTabIdForUrl(
  serviceWorker: Worker,
  urlPrefix: string,
): Promise<number> {
  const tabId = await serviceWorker.evaluate(async (prefix) => {
    const tabs = await chrome.tabs.query({});
    const hit = tabs.find((t) => (t.url || "").startsWith(prefix));
    return hit?.id ?? null;
  }, urlPrefix);
  if (tabId == null) throw new Error(`no chrome tab for ${urlPrefix}`);
  return tabId;
}

export async function postBrowserWait(
  body: Record<string, unknown>,
): Promise<Record<string, unknown>> {
  const res = await fetch(`${hostBase()}/v1/browser`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...body, wait: true, wait_timeout_sec: 30 }),
  });
  const json = (await res.json()) as Record<string, unknown>;
  if (!res.ok) {
    throw new Error(`browser wait failed: ${res.status} ${JSON.stringify(json)}`);
  }
  return json;
}
