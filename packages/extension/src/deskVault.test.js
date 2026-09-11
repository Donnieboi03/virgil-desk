import { describe, it, expect } from "vitest";
import { addVaultFile, getVaultFile, loadVault, VAULT_KEY } from "./deskVault.js";

function memStorage() {
  const store = {};
  return {
    async get(key) {
      if (typeof key === "string") return { [key]: store[key] };
      return { ...store };
    },
    async set(obj) {
      Object.assign(store, obj);
    },
    _store: store,
  };
}

describe("deskVault", () => {
  it("adds and loads a file by id", async () => {
    const storage = memStorage();
    const entry = await addVaultFile(
      { name: "resume.pdf", mime: "application/pdf", base64: btoa("hello") },
      storage,
    );
    expect(entry.id).toMatch(/^vault_/);
    const got = await getVaultFile(entry.id, storage);
    expect(got?.name).toBe("resume.pdf");
    const vault = await loadVault(storage);
    expect(vault.files).toHaveLength(1);
    expect(storage._store[VAULT_KEY].files).toHaveLength(1);
  });
});
