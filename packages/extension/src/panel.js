function renderColumn(el, items) {
  el.innerHTML = "";
  for (const item of items) {
    const li = document.createElement("li");
    li.textContent = item.title;
    if (item.proposals?.length) {
      for (const p of item.proposals) {
        const accept = document.createElement("button");
        accept.textContent = "Accept";
        accept.onclick = () =>
          chrome.runtime.sendMessage({
            type: "acceptProposal",
            itemId: item.id,
            proposalId: p.id,
            runId: item.run_id || "",
          });
        li.appendChild(accept);
      }
    }
    el.appendChild(li);
  }
}

async function refresh() {
  const { board } = await chrome.runtime.sendMessage({ type: "getBoard" });
  renderColumn(document.getElementById("col-you"), board.you || []);
  renderColumn(document.getElementById("col-agent"), board.agent || []);
  renderColumn(document.getElementById("col-waiting"), board.waiting || []);
}

document.getElementById("handoff").addEventListener("click", async () => {
  await chrome.runtime.sendMessage({ type: "handoffTab" });
  setTimeout(refresh, 800);
});

chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "boardUpdated") refresh();
});

refresh();
