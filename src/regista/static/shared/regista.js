// Shared by the Product (/) and the Studio (/studio): escaping, football labels, the API helper, and the Studio key.
// Plain script, no build step: it defines window.Regista.
(function () {
  // Everything that reaches innerHTML from the API goes through esc(): names, titles, tags, notes, verdict authors and
  // model output can come from uploads, reviewers or models, so they are never trusted as markup.
  const esc = (v) => String(v ?? '').replace(/[&<>"'`]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '`': '&#96;' }[c]));

  // People read these, never snake_case.
  const REASONS = { on_ball_main: 'On the ball', replay_appearance: 'Replay', highlight_appearance: 'Highlight', closeup_appearance: 'Closeup' };
  const TAGS = { take_on: 'Take-on', kick_off: 'Kick-off', skill_move: 'Skill move', ball_won: 'Ball won', key_pass: 'Key pass',
                 on_ball_main: 'On the ball', replay_appearance: 'Replay', highlight_appearance: 'Highlight', closeup_appearance: 'Closeup' };
  const words = (t) => { const s = String(t ?? '').replace(/_/g, ' '); return s.charAt(0).toUpperCase() + s.slice(1); };
  const reasonLabel = (r) => REASONS[r] || words(r);
  const tagLabel = (t) => TAGS[t] || words(t);

  // The Studio key lives in sessionStorage (gone when the tab closes) and travels only in the X-Regista-Token header.
  const KEY = 'regista-key';
  const key = {
    get() { try { return sessionStorage.getItem(KEY); } catch (e) { return null; } },
    set(v) { try { sessionStorage.setItem(KEY, v); } catch (e) {} },
    clear() { try { sessionStorage.removeItem(KEY); } catch (e) {} },
  };

  class ApiError extends Error {
    constructor(status, detail) { super(typeof detail === 'string' ? detail : `HTTP ${status}`); this.status = status; this.detail = detail; }
  }

  // api('/api/x') for a JSON GET; api('/api/x', { method: 'POST', body: {...}, auth: true }) sends the Studio key.
  async function api(path, opts = {}) {
    const headers = {};
    if (opts.body !== undefined && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json';
    if (opts.auth && key.get()) headers['X-Regista-Token'] = key.get();
    const body = opts.body === undefined ? undefined : (opts.body instanceof FormData ? opts.body : JSON.stringify(opts.body));
    const r = await fetch(path, { method: opts.method || 'GET', headers, body });
    const text = await r.text();
    let data = text;
    try { data = text ? JSON.parse(text) : null; } catch (e) {}
    if (!r.ok) throw new ApiError(r.status, data && data.detail !== undefined ? data.detail : data);
    return data;
  }

  // Images behind the Studio key (Who's who crops) cannot be loaded by <img src>, which sends no header: fetch them.
  async function authedObjectUrl(path) {
    const r = await fetch(path, { headers: key.get() ? { 'X-Regista-Token': key.get() } : {} });
    if (!r.ok) throw new ApiError(r.status, `HTTP ${r.status}`);
    return URL.createObjectURL(await r.blob());
  }

  const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;

  window.Regista = { esc, reasonLabel, tagLabel, key, api, ApiError, authedObjectUrl, fmtTime };
})();
