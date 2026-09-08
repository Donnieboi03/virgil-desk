chrome.storage.sync.get(["hostUrl"], (data) => {
  const el = document.getElementById("hostUrl");
  if (data.hostUrl) el.value = data.hostUrl;
  else el.value = "http://127.0.0.1:8787";
});
document.getElementById("save").addEventListener("click", () => {
  let hostUrl = document.getElementById("hostUrl").value.trim();
  if (!hostUrl) hostUrl = "http://127.0.0.1:8787";
  document.getElementById("hostUrl").value = hostUrl;
  chrome.storage.sync.set({ hostUrl });
});
