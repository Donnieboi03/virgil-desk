/**
 * Extension document vault — operator-supplied files for upload Hands.
 * Bytes stay in chrome.storage.local (base64); agents reference by vault id.
 */

export const VAULT_KEY = "virgil_desk_vault_v1";

/**
 * @typedef {{ id: string, name: string, mime: string, base64: string, added_at: string }} VaultEntry
 */

/** @returns {Promise<{ files: VaultEntry[] }>} */
export async function loadVault(storage = chrome.storage.local) {
  const data = await storage.get(VAULT_KEY);
  const raw = data[VAULT_KEY];
  if (!raw || !Array.isArray(raw.files)) return { files: [] };
  return { files: raw.files };
}

/** @param {{ files: VaultEntry[] }} vault */
export async function saveVault(vault, storage = chrome.storage.local) {
  await storage.set({ [VAULT_KEY]: { files: vault.files || [] } });
}

/**
 * @param {{ name: string, mime?: string, base64: string }} file
 * @returns {Promise<VaultEntry>}
 */
export async function addVaultFile(file, storage = chrome.storage.local) {
  const vault = await loadVault(storage);
  const entry = {
    id: `vault_${crypto.randomUUID().replace(/-/g, "").slice(0, 12)}`,
    name: String(file.name || "file").slice(0, 200),
    mime: String(file.mime || "application/octet-stream").slice(0, 120),
    base64: String(file.base64 || ""),
    added_at: new Date().toISOString(),
  };
  if (!entry.base64) throw new Error("vault file missing base64");
  vault.files.push(entry);
  await saveVault(vault, storage);
  return entry;
}

/**
 * @param {string} id
 * @returns {Promise<VaultEntry | null>}
 */
export async function getVaultFile(id, storage = chrome.storage.local) {
  const vault = await loadVault(storage);
  return vault.files.find((f) => f.id === id) || null;
}

/**
 * Build a File from vault entry for DataTransfer injection.
 * @param {VaultEntry} entry
 */
export function vaultEntryToFile(entry) {
  const bin = atob(entry.base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new File([bytes], entry.name, { type: entry.mime || "application/octet-stream" });
}
