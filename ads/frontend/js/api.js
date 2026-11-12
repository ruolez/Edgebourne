// Fetch wrapper: JSON in/out, sends people to sign in on 401.
export class ApiError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body || {}; }
}

// reuse: a polled GET sends the ETag of its last answer; an unchanged answer comes back as 304 with no
// body and is read again from the copy kept here (a fresh object each time, callers may change it).
const kept = new Map();

export async function api(path, { method = "GET", body, reuse = false } = {}) {
  let res;
  const last = reuse && method === "GET" ? kept.get(path) : null;
  try { res = await fetch(path, {
    method,
    // X-Requested-With: the server refuses writes without it (cross-site request guard).
    headers: { "X-Requested-With": "ebads", ...(body !== undefined ? { "Content-Type": "application/json" } : {}), ...(last ? { "If-None-Match": last.etag } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  }); } catch (e) { throw new ApiError("Can't reach the server. Check your connection and try again.", 0); }
  if (last && res.status === 304) return JSON.parse(last.text);
  let data = null;
  let text = "";
  try { text = await res.text(); data = JSON.parse(text); } catch (e) { data = null; }
  if (reuse && res.ok && data !== null && res.headers.get("ETag")) kept.set(path, { etag: res.headers.get("ETag"), text });
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search + location.hash);
    throw new ApiError("Sign in to continue", 401, data);
  }
  if (!res.ok) throw new ApiError((data && data.error) || `Request failed (${res.status})`, res.status, data);
  return data;
}
