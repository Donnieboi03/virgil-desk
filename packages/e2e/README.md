# E2E (optional nightly)

Manual checklist for live Chrome + Host (M2+):

1. Handoff = snapshot only; no duplicate until agent needs same page
2. Different URL → `openTab` in Agent group (not duplicate)
3. Same-page agent work → `duplicateTab`; human tab untouched
4. Post-click `command_result` includes scrape + screenshot
5. Board shows You / Agent / Waiting; Accept without Notion
6. Human tab never receives agent ops (policy test)
7. Board persists after Chrome restart (`storage.local`)
8. `desk-events --run-id …` shows screenshot metadata
9. Hermes `skill_manage` works after handoff

Automated Playwright E2E is deferred until unpacked-extension CI lane is stable.
