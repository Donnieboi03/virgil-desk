/**
 * Page-context observe + act bundle (WebMarker SoM + Anthropic-style targets).
 * Bundled to dist/interactObserve.bundle.js for chrome.scripting.executeScript.
 */
import { mark, unmark, isMarked } from "webmarker-js";

const INTERACTIVE_SELECTOR =
  "a[href], button, input, textarea, select, [role=button], [role=link], " +
  "[role=checkbox], [role=radio], [role=tab], [role=menuitem], [role=row], " +
  "[role=option], [contenteditable=true], [tabindex]:not([tabindex='-1'])";

function viewportInfo() {
  return {
    w: window.innerWidth,
    h: window.innerHeight,
    devicePixelRatio: window.devicePixelRatio || 1,
  };
}

function rectFromEl(el) {
  const r = el.getBoundingClientRect();
  return {
    x: Math.round(r.x),
    y: Math.round(r.y),
    w: Math.round(r.width),
    h: Math.round(r.height),
  };
}

function centerFromRect(rect) {
  return {
    x: Math.round(rect.x + rect.w / 2),
    y: Math.round(rect.y + rect.h / 2),
  };
}

function isVisible(el) {
  const r = el.getBoundingClientRect();
  if (r.width < 2 || r.height < 2) return false;
  if (r.bottom < 0 || r.right < 0 || r.top > window.innerHeight || r.left > window.innerWidth) {
    return false;
  }
  const style = window.getComputedStyle(el);
  if (style.visibility === "hidden" || style.display === "none" || style.opacity === "0") {
    return false;
  }
  return true;
}

function isOccluded(el, center) {
  const hit = document.elementFromPoint(center.x, center.y);
  if (!hit) return true;
  return !(hit === el || el.contains(hit) || hit.contains(el));
}

function labelFor(el) {
  const aria = el.getAttribute("aria-label");
  if (aria) return aria.slice(0, 200);
  const labelledBy = el.getAttribute("aria-labelledby");
  if (labelledBy) {
    const ref = document.getElementById(labelledBy);
    if (ref?.textContent) return ref.textContent.trim().slice(0, 200);
  }
  if (el.id) {
    const lab = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (lab?.textContent) return lab.textContent.trim().slice(0, 200);
  }
  const title = el.getAttribute("title");
  if (title) return title.slice(0, 200);
  const text = (el.innerText || el.textContent || "").trim();
  if (text) return text.slice(0, 200);
  const tag = el.tagName.toLowerCase();
  const role = el.getAttribute("role") || tag;
  return `${role} element`;
}

function kindFor(el) {
  const tag = el.tagName.toLowerCase();
  if (tag === "input") {
    const t = (el.getAttribute("type") || "text").toLowerCase();
    if (t === "checkbox" || t === "radio") return "toggle";
    return "input";
  }
  if (tag === "textarea" || tag === "select") return tag === "select" ? "select" : "input";
  const role = (el.getAttribute("role") || "").toLowerCase();
  if (role === "checkbox" || role === "radio" || role === "switch") return "toggle";
  if (role === "combobox" || role === "listbox") return "select";
  return "clickable";
}

function selectorHint(el) {
  if (el.id && !/\d{3,}/.test(el.id)) return `#${CSS.escape(el.id)}`;
  const name = el.getAttribute("name");
  if (name) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\"')}"]`;
  const aria = el.getAttribute("aria-label");
  if (aria) return `[aria-label="${aria.replace(/"/g, '\\"')}"]`;
  return "";
}

function selectorStable(el, hint) {
  if (!hint) return false;
  if (el.id && !/\d{3,}/.test(el.id)) return true;
  if (el.getAttribute("name")) return true;
  if (el.getAttribute("aria-label")) return true;
  return false;
}

function findScrollContainers(max) {
  const out = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll("*")) {
      if (out.length >= max) return;
      const style = window.getComputedStyle(el);
      const oy = style.overflowY;
      if (oy !== "auto" && oy !== "scroll") continue;
      if (el.scrollHeight <= el.clientHeight + 4) continue;
      if (!isVisible(el)) continue;
      const rect = rectFromEl(el);
      const center = centerFromRect(rect);
      if (isOccluded(el, center)) continue;
      out.push({
        id: out.length + 1,
        ref: `s${out.length + 1}`,
        label: labelFor(el),
        rect,
        scrollHeight: el.scrollHeight,
        clientHeight: el.clientHeight,
        _el: el,
      });
    }
  };
  walk(document);
  return out.map(({ _el, ...rest }) => rest);
}

function buildTargetsFromMarked(marked, maxTargets) {
  const entries = Object.entries(marked).slice(0, maxTargets);
  return entries.map(([label, entry], idx) => {
    const el = entry.element;
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    const hint = selectorHint(el);
    return {
      id: idx + 1,
      ref: `t${idx + 1}`,
      mark_label: label,
      kind: kindFor(el),
      label: labelFor(el),
      text: (el.innerText || el.textContent || "").trim().slice(0, 500),
      role: el.getAttribute("role") || undefined,
      tag: el.tagName.toLowerCase(),
      rect,
      center,
      selector_hint: hint || undefined,
      selector_stable: selectorStable(el, hint),
    };
  });
}

function heuristicScan(maxTargets) {
  const seen = new Set();
  const candidates = [];
  const addEl = (el) => {
    if (!el || seen.has(el)) return;
    seen.add(el);
    if (!isVisible(el)) return;
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    if (isOccluded(el, center)) return;
    candidates.push(el);
  };
  document.querySelectorAll(INTERACTIVE_SELECTOR).forEach(addEl);
  return candidates.slice(0, maxTargets).map((el, idx) => {
    const rect = rectFromEl(el);
    const center = centerFromRect(rect);
    const hint = selectorHint(el);
    return {
      id: idx + 1,
      ref: `t${idx + 1}`,
      kind: kindFor(el),
      label: labelFor(el),
      text: (el.innerText || el.textContent || "").trim().slice(0, 500),
      role: el.getAttribute("role") || undefined,
      tag: el.tagName.toLowerCase(),
      rect,
      center,
      selector_hint: hint || undefined,
      selector_stable: selectorStable(el, hint),
    };
  });
}

export function deskObserve(opts = {}) {
  const maxTargets = opts.maxTargets ?? 80;
  const annotate = opts.annotate !== false;
  let interact_targets = [];
  try {
    if (annotate) {
      if (isMarked()) unmark();
      const marked = mark({
        selector: INTERACTIVE_SELECTOR,
        viewPortOnly: true,
        getLabel: (_el, index) => String(index),
        markAttribute: "data-desk-mark-label",
      });
      interact_targets = buildTargetsFromMarked(marked, maxTargets);
    } else {
      interact_targets = heuristicScan(maxTargets);
    }
  } catch {
    interact_targets = heuristicScan(maxTargets);
  }
  const scroll_containers = findScrollContainers(20).map((s, i) => ({
    ...s,
    id: i + 1,
    ref: `s${i + 1}`,
  }));
  const vp = viewportInfo();
  return {
    url: location.href,
    title: document.title,
    viewport: { w: vp.w, h: vp.h },
    device_pixel_ratio: vp.devicePixelRatio,
    interact_targets,
    scroll_containers,
    marked: annotate && isMarked(),
  };
}

export function deskUnmark() {
  try {
    if (isMarked()) unmark();
  } catch {
    /* ignore */
  }
}

function resolveTarget(targets, params) {
  if (params.target_id != null) {
    const t = targets.find((x) => x.id === params.target_id);
    if (t) return { target: t, used: "target_id" };
  }
  if (params.ref) {
    const t = targets.find((x) => x.ref === params.ref);
    if (t) return { target: t, used: "ref" };
  }
  const text = params.text || params.contains;
  if (text) {
    const lower = String(text).toLowerCase();
    const t = targets.find(
      (x) =>
        x.label?.toLowerCase().includes(lower) ||
        x.text?.toLowerCase().includes(lower),
    );
    if (t) return { target: t, used: "text" };
  }
  if (params.selector && params.selector_stable) {
    const el = document.querySelector(params.selector);
    if (el) return { element: el, used: "selector" };
  }
  if (params.x != null && params.y != null) {
    return { point: { x: params.x, y: params.y }, used: "coordinates" };
  }
  return { error: "stale_observe: could not resolve target" };
}

function elementFromTarget(target) {
  if (target.mark_label != null) {
    const el = document.querySelector(`[data-desk-mark-label="${target.mark_label}"]`);
    if (el) return el;
  }
  if (target.selector_hint && target.selector_stable) {
    const el = document.querySelector(target.selector_hint);
    if (el) return el;
  }
  const { center } = target;
  return document.elementFromPoint(center.x, center.y);
}

function dispatchClick(el) {
  el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  const rect = el.getBoundingClientRect();
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  for (const type of ["pointerdown", "mousedown", "pointerup", "mouseup", "click"]) {
    el.dispatchEvent(
      new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        view: window,
        clientX: x,
        clientY: y,
      }),
    );
  }
  if (typeof el.click === "function") el.click();
}

function reactFill(el, value) {
  el.focus();
  const tag = el.tagName.toLowerCase();
  if (tag === "input" || tag === "textarea") {
    const setter = Object.getOwnPropertyDescriptor(
      tag === "input" ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype,
      "value",
    )?.set;
    if (setter) setter.call(el, value);
    else el.value = value;
    el.dispatchEvent(
      new InputEvent("input", {
        bubbles: true,
        cancelable: true,
        inputType: "insertText",
        data: value,
      }),
    );
    el.dispatchEvent(new Event("change", { bubbles: true }));
    el.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }
  if (el.isContentEditable) {
    el.textContent = value;
    el.dispatchEvent(new InputEvent("input", { bubbles: true }));
    return true;
  }
  return false;
}

export function deskAct(op, params, targets, urlBefore) {
  const resolved = resolveTarget(targets, params);
  if (resolved.error) {
    return { ok: false, error: resolved.error, act_resolved: { op, requested: params, used: "none" } };
  }
  let hit = {};
  try {
    if (op === "scroll") {
      const dir = params.direction === "up" ? -1 : 1;
      const ratio = params.ratio ?? 0.85;
      if (resolved.target?.kind === "scroll_container") {
        const el = elementFromTarget(resolved.target);
        if (el) el.scrollBy(0, dir * el.clientHeight * ratio);
        hit = { ref: resolved.target.ref };
      } else {
        window.scrollBy(0, dir * window.innerHeight * ratio);
        hit = { tag: "window" };
      }
      return {
        ok: true,
        act_resolved: {
          op,
          requested: params,
          used: resolved.used,
          hit,
          url_before: urlBefore,
          url_after: location.href,
        },
      };
    }
    if (op === "key") {
      const key = params.key || "Enter";
      const target = document.activeElement || document.body;
      target.dispatchEvent(
        new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }),
      );
      target.dispatchEvent(
        new KeyboardEvent("keyup", { key, bubbles: true, cancelable: true }),
      );
      return {
        ok: true,
        act_resolved: {
          op,
          requested: params,
          used: "key",
          hit: { tag: target.tagName?.toLowerCase() },
          url_before: urlBefore,
          url_after: location.href,
        },
      };
    }
    let el = resolved.element;
    if (!el && resolved.target) el = elementFromTarget(resolved.target);
    if (!el && resolved.point) el = document.elementFromPoint(resolved.point.x, resolved.point.y);
    if (!el) {
      return {
        ok: false,
        error: "element not found at target",
        act_resolved: { op, requested: params, used: resolved.used },
      };
    }
    hit = {
      ref: resolved.target?.ref,
      tag: el.tagName?.toLowerCase(),
      center: centerFromRect(rectFromEl(el)),
    };
    if (op === "click") {
      dispatchClick(el);
    } else if (op === "fill") {
      if (!reactFill(el, params.value ?? "")) {
        return { ok: false, error: "fill not supported on element", act_resolved: { op, requested: params, used: resolved.used } };
      }
    } else {
      return { ok: false, error: `unknown op: ${op}` };
    }
    return {
      ok: true,
      act_resolved: {
        op,
        requested: params,
        used: resolved.used,
        hit,
        url_before: urlBefore,
        url_after: location.href,
      },
    };
  } catch (err) {
    return {
      ok: false,
      error: String(err),
      act_resolved: { op, requested: params, used: resolved.used || "none" },
    };
  }
}

// UMD-style global for executeScript world injection
if (typeof globalThis !== "undefined") {
  globalThis.deskObserve = deskObserve;
  globalThis.deskUnmark = deskUnmark;
  globalThis.deskAct = deskAct;
}
