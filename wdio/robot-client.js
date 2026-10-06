// Cliente JS do servidor do robô (server.py). Requer Node 18+ (fetch nativo).
// Coordenadas em PIXELS da tela do celular, as mesmas do element.rect do Appium.

class RobotClient {
  constructor(baseUrl = process.env.ROBOT_URL || 'http://127.0.0.1:8765', timeoutMs = 60000) {
    this.baseUrl = baseUrl.replace(/\/$/, '');
    this.timeoutMs = timeoutMs;
  }

  async _request(method, path, body) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(this.timeoutMs),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(`robô: ${data.error || `HTTP ${res.status}`}`);
    }
    return data;
  }

  health() { return this._request('GET', '/health'); }
  tap(x, y, { dwellMs } = {}) { return this._request('POST', '/tap', { x, y, dwell_ms: dwellMs }); }
  longPress(x, y, seconds = 1) { return this._request('POST', '/long_press', { x, y, seconds }); }
  swipe(x1, y1, x2, y2, durationS = 0.35) {
    return this._request('POST', '/swipe', { x1, y1, x2, y2, duration_s: durationS });
  }
  park() { return this._request('POST', '/park', {}); }
}

module.exports = { RobotClient };
