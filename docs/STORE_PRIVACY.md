# Chrome Web Store privacy (draft)

Virgil Desk collects and processes data as follows:

## Data stored locally

- **Board state** (`chrome.storage.local`): work items you see in the side panel (You / Agent / Waiting).
- **Desk memory** (`chrome.storage.local` key `virgil_desk_memory_v1`): last few execute summaries and per-handoff notepad bullets shared across agent tasks.
- **Desk semantic facts** (`chrome.storage.local` key `virgil_desk_semantic_v1`): optional standing prefs/decisions (key/value/tags). Do **not** store secrets, passwords, or payment data. See [`MEMORY.md`](MEMORY.md).
- **Tab session map** (`chrome.storage.session`): pairs human tab ↔ agent tab for the current browser session only.
- **Host URL** (`chrome.storage.sync`): optional setting for your local Virgil Host address (default `http://127.0.0.1:8787`).

## Data sent to your Host

On **hand off this tab**, the extension sends to your local Host (never to Virgil cloud by default):

- Page URL and title
- Bounded text excerpt and link list from the active tab (read-only snapshot)
- Tab and window identifiers for tab-group routing

Browser commands return scrape excerpts and PNG screenshots (base64) to the Host for agent verification. The extension does **not** write files to disk.

## Permissions justification

| Permission | Why |
|------------|-----|
| `tabs` / `tabGroups` | Route agent work into a collapsed **Virgil · Agent** group in your window |
| `scripting` | Read-only snapshot on handoff; scrape/screenshot on **agent tabs only** |
| `storage` | Persist board between sessions |
| `sidePanel` | You / Agent / Waiting desk UI |
| `host_permissions` localhost | Connect to your local Virgil Host |

## Not collected

- No analytics SDK in MVP
- No passwords, payment fields, or send/submit automation on your tab
- No third-party cloud unless you configure an agent backend that uses one

## Operator control

Uninstall the extension or clear extension data in Chrome to remove local board state. Host logs live under `~/.virgil-desk/logs/` on your machine.
