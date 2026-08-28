chrome.storage.sync.get(["hostUrl"], (data) => {
  if (data.hostUrl) document.getElementById("hostUrl").value = data.hostUrl;
});
document.getElementById("save").addEventListener("click", () => {
  const hostUrl = document.getElementById("hostUrl").value;
  chrome.storage.sync.set({ hostUrl });
});
