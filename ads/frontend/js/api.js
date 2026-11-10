// Fetch wrapper: JSON in/out, sends people to sign in on 401.
export class ApiError extends Error {
  constructor(message, status, body) { super(message); this.status = status; this.body = body || {}; }
}

export async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    // X-Requested-With: the server refuses writes without it (cross-site request guard).
    headers: { "X-Requested-With": "ebads", ...(body !== undefined ? { "Content-Type": "application/json" } : {}) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
    credentials: "same-origin",
  });
  let data = null;
  try { data = await res.json(); } catch (e) { data = null; }
  if (res.status === 401 && !path.startsWith("/api/auth/login")) {
    location.href = "/login.html?next=" + encodeURIComponent(location.pathname + location.search + location.hash);
    throw new ApiError("Sign in to continue", 401, data);
  }
  if (!res.ok) throw new ApiError((data && data.error) || `Request failed (${res.status})`, res.status, data);
  return data;
}
