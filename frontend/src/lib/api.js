export async function api(path, { method = 'GET', body, allow401 = false } = {}) {
  const res = await fetch('/api' + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
    credentials: 'same-origin',
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (res.status === 401 && !allow401) window.dispatchEvent(new Event('mt-logout'));
  if (!res.ok) {
    const msg = typeof data?.detail === 'string' ? data.detail : `Error ${res.status}`;
    throw new Error(msg);
  }
  return data;
}
