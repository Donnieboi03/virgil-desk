/** Origin compare for off-origin popup quarantine. */

export function originOf(url) {
  try {
    return new URL(url).origin;
  } catch {
    return "";
  }
}

/**
 * Close spawned tab when its URL origin differs from the handoff page.
 * Empty / about:blank URLs are not closed yet (wait for navigation).
 */
export function shouldCloseSpawnedTab(handoffUrl, newUrl) {
  if (!handoffUrl || !newUrl) return false;
  const lower = String(newUrl).toLowerCase();
  if (lower === "about:blank" || lower.startsWith("chrome://") || lower.startsWith("chrome-extension://")) {
    return false;
  }
  const handoffOrigin = originOf(handoffUrl);
  const newOrigin = originOf(newUrl);
  if (!handoffOrigin || !newOrigin) return false;
  return handoffOrigin !== newOrigin;
}
