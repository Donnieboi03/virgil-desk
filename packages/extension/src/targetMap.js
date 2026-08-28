/** Ephemeral observe target maps keyed by run_id:tab_id (service worker). */

const targetMaps = new Map();

export function mapKey(runId, tabId) {
  return `${runId}:${tabId}`;
}

export function storeTargetMap(runId, tabId, payload) {
  const key = mapKey(runId, tabId);
  targetMaps.set(key, {
    interact_targets: payload.interact_targets || [],
    scroll_containers: payload.scroll_containers || [],
    url: payload.url,
    ts: Date.now(),
  });
}

export function getTargetMap(runId, tabId) {
  return targetMaps.get(mapKey(runId, tabId));
}

export function clearTargetMap(runId, tabId) {
  targetMaps.delete(mapKey(runId, tabId));
}

export function clearMapsForTab(tabId) {
  for (const key of [...targetMaps.keys()]) {
    if (key.endsWith(`:${tabId}`)) targetMaps.delete(key);
  }
}
