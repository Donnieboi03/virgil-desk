const params = new URLSearchParams(location.search);
const tabId = Number(params.get("tab"));
const itemId = params.get("item") || undefined;
const runId = params.get("run") || undefined;

const result = await chrome.runtime.sendMessage({
  type: "revealAgentTab",
  tabId,
  itemId,
  runId,
});

if (!result?.ok) {
  document.body.textContent = result?.error || "Could not open that tab (it may have been closed).";
} else {
  window.close();
}
