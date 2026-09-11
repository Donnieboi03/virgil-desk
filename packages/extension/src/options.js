import {
  SEMANTIC_KEY,
  emptySemantic,
  upsertFact,
  deleteFact,
} from "./deskMemory.js";

const MAX_FACTS = 20;
const MAX_KEY = 64;
const MAX_VALUE = 200;

chrome.storage.sync.get(["hostUrl"], (data) => {
  const el = document.getElementById("hostUrl");
  if (data.hostUrl) el.value = data.hostUrl;
  else el.value = "http://127.0.0.1:8787";
});

document.getElementById("save").addEventListener("click", () => {
  let hostUrl = document.getElementById("hostUrl").value.trim();
  if (!hostUrl) hostUrl = "http://127.0.0.1:8787";
  document.getElementById("hostUrl").value = hostUrl;
  chrome.storage.sync.set({ hostUrl }, () => {
    document.getElementById("hostStatus").textContent = "Saved.";
  });
});

chrome.storage.sync.get(["notifyHumanAttention"], (data) => {
  document.getElementById("notifyHuman").checked = data.notifyHumanAttention === true;
});

document.getElementById("notifyHuman").addEventListener("change", (ev) => {
  const on = Boolean(ev.target.checked);
  chrome.storage.sync.set({ notifyHumanAttention: on }, () => {
    document.getElementById("notifyStatus").textContent = on
      ? "Notifications enabled (local override)."
      : "Notifications off (unless Host config enables them).";
  });
});

function fileToBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      const base64 = dataUrl.includes(",") ? dataUrl.split(",")[1] : dataUrl;
      resolve(base64);
    };
    reader.onerror = () => reject(reader.error || new Error("read failed"));
    reader.readAsDataURL(file);
  });
}

async function refreshVault() {
  const res = await chrome.runtime.sendMessage({ type: "listVault" });
  const root = document.getElementById("vaultList");
  if (!res?.ok) {
    root.textContent = res?.error || "Vault unavailable.";
    return;
  }
  const files = res.files || [];
  if (!files.length) {
    root.innerHTML = "<p class=\"fact-meta\">No files yet.</p>";
    return;
  }
  root.innerHTML = files
    .map(
      (f) =>
        `<div class="fact"><div class="fact-body"><div class="fact-key">${f.name}</div>` +
        `<div class="fact-meta">${f.id} · ${f.mime || ""} · ${f.added_at || ""}</div></div></div>`,
    )
    .join("");
}

document.getElementById("addVault").addEventListener("click", async () => {
  const input = document.getElementById("vaultFile");
  const file = input.files?.[0];
  if (!file) {
    document.getElementById("vaultStatus").textContent = "Choose a file first.";
    return;
  }
  try {
    const base64 = await fileToBase64(file);
    const res = await chrome.runtime.sendMessage({
      type: "addVaultFile",
      name: file.name,
      mime: file.type || "application/octet-stream",
      base64,
    });
    if (!res?.ok) {
      document.getElementById("vaultStatus").textContent = res?.error || "Add failed.";
      return;
    }
    input.value = "";
    document.getElementById("vaultStatus").textContent = `Added ${res.file.name} (${res.file.id}).`;
    await refreshVault();
  } catch (err) {
    document.getElementById("vaultStatus").textContent = String(err);
  }
});

refreshVault();

async function loadSemantic() {
  const data = await chrome.storage.local.get(SEMANTIC_KEY);
  return data[SEMANTIC_KEY] || emptySemantic();
}

async function saveSemantic(semantic) {
  await chrome.storage.local.set({ [SEMANTIC_KEY]: semantic });
}

function renderFacts(semantic) {
  const root = document.getElementById("facts");
  const facts = [...(semantic.facts || [])].sort((a, b) =>
    String(b.updated_at || "").localeCompare(String(a.updated_at || "")),
  );
  if (!facts.length) {
    root.innerHTML = "<p class=\"fact-meta\">No facts yet.</p>";
    return;
  }
  root.innerHTML = "";
  for (const fact of facts) {
    const row = document.createElement("div");
    row.className = "fact";
    const body = document.createElement("div");
    body.className = "fact-body";
    const keyEl = document.createElement("div");
    keyEl.className = "fact-key";
    keyEl.textContent = fact.key || "";
    const valEl = document.createElement("div");
    valEl.textContent = fact.value || "";
    const meta = document.createElement("div");
    meta.className = "fact-meta";
    meta.textContent = `tags: ${(fact.tags || []).join(", ") || "—"} · ${fact.source || "manual"} · ${fact.updated_at || ""}`;
    body.append(keyEl, valEl, meta);
    const del = document.createElement("button");
    del.type = "button";
    del.textContent = "Delete";
    del.addEventListener("click", async () => {
      const next = deleteFact(await loadSemantic(), { key: fact.key });
      await saveSemantic(next);
      document.getElementById("factStatus").textContent = `Deleted ${fact.key}.`;
      renderFacts(next);
    });
    row.append(body, del);
    root.append(row);
  }
}

document.getElementById("addFact").addEventListener("click", async () => {
  const key = document.getElementById("factKey").value.trim();
  const value = document.getElementById("factValue").value.trim();
  const tagsRaw = document.getElementById("factTags").value;
  const tags = tagsRaw.split(",").map((t) => t.trim()).filter(Boolean);
  if (!key || !value) {
    document.getElementById("factStatus").textContent = "Key and value required.";
    return;
  }
  const next = upsertFact(await loadSemantic(), {
    key,
    value,
    tags,
    source: "manual",
    maxFacts: MAX_FACTS,
    maxKeyChars: MAX_KEY,
    maxValueChars: MAX_VALUE,
  });
  await saveSemantic(next);
  document.getElementById("factKey").value = "";
  document.getElementById("factValue").value = "";
  document.getElementById("factStatus").textContent = `Saved ${key}.`;
  renderFacts(next);
});

loadSemantic().then(renderFacts);
