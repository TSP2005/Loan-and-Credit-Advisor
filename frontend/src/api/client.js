const API_BASE = 'http://localhost:8000';

/* ===== HTTP helpers ===== */
function getHeaders(token) {
  const h = { 'Content-Type': 'application/json' };
  if (token) h['Authorization'] = `Bearer ${token}`;
  return h;
}

export async function apiPost(path, body, token = null) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: getHeaders(token),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

export async function apiGet(path, token = null) {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'GET',
    headers: getHeaders(token),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Request failed');
  return data;
}

export async function apiUpload(path, file, token) {
  const form = new FormData();
  form.append('file', file);
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || 'Upload failed');
  return data;
}

/* ===== WebSocket ===== */
export function createChatSocket(userId, onMessage, onError) {
  const ws = new WebSocket(`ws://localhost:8000/ws/chat/${userId}`);
  
  ws.onopen = () => {
    console.log(`EVENT | WEBSOCKET | action=connected | user_id=${userId}`);
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    console.log(`EVENT | WEBSOCKET | direction=receive | type=${data.type} | length=${event.data.length}`);
    onMessage(data);
  };

  ws.onerror = (err) => {
    console.error('EVENT | WEBSOCKET | action=error', err);
    if (onError) onError(err);
  };

  ws.onclose = () => {
    console.log(`EVENT | WEBSOCKET | action=disconnected | user_id=${userId}`);
  };

  return ws;
}

/* ===== Frontend logging ===== */
export function sendLog(level, component, action, details) {
  console.log(`${new Date().toISOString()} | ${level} | ${component} | ${action} | ${details}`);
  // Fire-and-forget to backend
  fetch(`${API_BASE}/logs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level, component, action, details, timestamp: new Date().toISOString() }),
  }).catch(() => {});
}
