// Page state in the URL, so a view can be bookmarked, shared and survives a reload.
// read(defaults) → values from ?query over the defaults; write(patch) replaces the URL without reloading.
export function read(defaults) {
  const q = new URLSearchParams(location.search);
  const out = { ...defaults };
  for (const [k, def] of Object.entries(defaults)) {
    if (!q.has(k)) continue;
    const v = q.get(k);
    out[k] = typeof def === "boolean" ? v === "1" : v;
  }
  return out;
}

// The URL of this page with the state written over its query.
export function url(state, defaults) {
  const q = new URLSearchParams(location.search);
  for (const [k, def] of Object.entries(defaults)) {
    const v = state[k];
    const s = typeof def === "boolean" ? (v ? "1" : "0") : String(v ?? "");
    if (v === def || v === null || v === undefined || s === "") q.delete(k); else q.set(k, s);
  }
  return location.pathname + (q.toString() ? `?${q}` : "") + location.hash;
}

// history.state is kept: it marks an open layer (below), which a plain state change must not forget.
export function write(state, defaults, { push = false } = {}) {
  history[push ? "pushState" : "replaceState"](push ? null : history.state, "", url(state, defaults));
}

// Things that open over a page (a lead on a phone, an Inbox item, the quick look) and that Back closes:
// opening one pushes a history entry, moving to another replaces it, closing it from the page steps back
// over the entry it pushed (so Back and Forward never land on a copy of the same screen). The page listens
// for popstate and shows whatever the URL now says.
export const inLayer = () => Boolean(history.state && history.state.layer);
export function openLayer(href) {
  history[inLayer() ? "replaceState" : "pushState"]({ layer: true }, "", href);
}
export function closeLayer(href) {
  if (inLayer()) { history.back(); return; }
  history.replaceState(history.state, "", href);
}
// The page moved on while a layer was open (another tab, level or filter): the entry stops being the layer's,
// so closing it later replaces the URL instead of stepping back to the view before.
export function leaveLayer() {
  if (inLayer()) history.replaceState(null, "", location.href);
}

export function query(state, defaults) {
  const q = new URLSearchParams();
  for (const [k, def] of Object.entries(defaults)) {
    const v = state[k];
    if (v !== def && v !== null && v !== undefined && v !== "") q.set(k, typeof def === "boolean" ? (v ? "1" : "0") : String(v));
  }
  return q.toString();
}
