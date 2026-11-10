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

export function write(state, defaults, { push = false } = {}) {
  const q = new URLSearchParams(location.search);
  for (const [k, def] of Object.entries(defaults)) {
    const v = state[k];
    const s = typeof def === "boolean" ? (v ? "1" : "0") : String(v ?? "");
    if (v === def || v === null || v === undefined || s === "") q.delete(k); else q.set(k, s);
  }
  const url = location.pathname + (q.toString() ? `?${q}` : "") + location.hash;
  history[push ? "pushState" : "replaceState"](null, "", url);
}

export function query(state, defaults) {
  const q = new URLSearchParams();
  for (const [k, def] of Object.entries(defaults)) {
    const v = state[k];
    if (v !== def && v !== null && v !== undefined && v !== "") q.set(k, typeof def === "boolean" ? (v ? "1" : "0") : String(v));
  }
  return q.toString();
}
