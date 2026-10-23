// Shared by every page (/, /me, /scout, /players/{id}, /studio): escaping, football labels, the API helper, the Studio
// key, the per-visitor store (Regista.store) and the left panel's sections (Regista.sections).
// Plain script, no build step: it defines window.Regista. Loading it touches no storage and, without a page, no DOM
// (tests run it in node).
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

  // The views panel (nav.views, shared/regista.css) sticks just below the page's header. Headers can differ in height and
  // some pages let theirs scroll away on narrow screens, so measure it: --top-h is
  // the header's height while it is sticky, 0 otherwise. Without this script the CSS default (52 px) applies.
  function trackHeader() {
    const head = document.querySelector('header.top');
    if (!head || !document.querySelector('nav.views')) return;
    const set = () => {
      const covers = /sticky|fixed/.test(getComputedStyle(head).position) ? head.getBoundingClientRect().height : 0;
      document.documentElement.style.setProperty('--top-h', `${covers}px`);
    };
    set();
    if (window.ResizeObserver) new ResizeObserver(set).observe(head);
    window.addEventListener('resize', set);
  }
  if (typeof document === 'undefined') { /* loaded without a page (tests run this file in node) */ }
  else if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', trackHeader);
  else trackHeader();

  // ------------------------------------------------------------------ the per-visitor store
  // What a visitor does on the dashboards that is theirs alone (messages, shortlist stages and notes, reports, a club's
  // needs, "My details" edits, settings) stays in THIS browser: localStorage under a versioned prefix, never sent to the
  // server. Storage can be missing or throw (private windows, blocked site data): every read and write is guarded, and
  // values then live in memory for the page's life, so the pages work the same, starting from the seeds.
  //   Regista.store.get(key, fallback)  the stored value (a copy), else fallback (a copy)
  //   Regista.store.set(key, value)     JSON-serialisable values only; returns true when the browser kept it
  //   Regista.store.reset()             forget every key under the prefix (the dashboards' "Reset this demo")
  //   Regista.store.watch(fn)           fn(key) when another tab of this browser changes a key
  const PREFIX = 'regista.demo.v1.';
  const memory = new Map();          // key -> JSON text; also what is read back when storage is blocked
  const copy = (v) => (v === undefined ? undefined : JSON.parse(JSON.stringify(v)));
  const ls = () => { try { return typeof localStorage === 'undefined' ? null : localStorage; } catch (e) { return null; } };
  const store = {
    prefix: PREFIX,
    get(k, fallback) {
      let text = null;
      try { const s = ls(); text = s ? s.getItem(PREFIX + k) : null; } catch (e) { text = null; }
      if (text === null && memory.has(k)) text = memory.get(k);
      if (text === null) return copy(fallback);
      try { return JSON.parse(text); } catch (e) { return copy(fallback); }
    },
    set(k, value) {
      const text = JSON.stringify(value);
      memory.set(k, text);
      try { const s = ls(); if (!s) return false; s.setItem(PREFIX + k, text); return true; } catch (e) { return false; }
    },
    remove(k) {
      memory.delete(k);
      try { const s = ls(); if (s) s.removeItem(PREFIX + k); } catch (e) {}
    },
    reset() {
      memory.clear();
      try {
        const s = ls();
        if (!s) return;
        const mine = [];
        for (let i = 0; i < s.length; i++) { const k = s.key(i); if (k && k.startsWith(PREFIX)) mine.push(k); }
        mine.forEach((k) => s.removeItem(k));
      } catch (e) {}
    },
    // Whether this browser keeps what is saved (false in a private window with storage blocked).
    persistent() {
      try { const s = ls(); if (!s) return false; s.setItem(PREFIX + '_probe', '1'); s.removeItem(PREFIX + '_probe'); return true; } catch (e) { return false; }
    },
    watch(fn) {
      if (typeof window.addEventListener !== 'function') return;
      window.addEventListener('storage', (e) => {
        if (e.key === null) fn(null);                                   // cleared everywhere
        else if (e.key.startsWith(PREFIX)) { memory.delete(e.key.slice(PREFIX.length)); fn(e.key.slice(PREFIX.length)); }
      });
    },
  };

  // ------------------------------------------------------------------ the left panel's sections
  // On /me and /scout the current view's link in nav.views has its sections under it (shared/regista.css):
  //   <a href="/me" class="parent" aria-current="page">Player profile</a>
  //   <div class="subviews" role="group" aria-label="Player profile sections">
  //     <a href="/me#overview" data-section="overview">Overview</a> ...
  //     <a href="/me#messages" data-section="messages">Messages <span class="count" data-count="messages"></span></a>
  //   </div>
  // Regista.sections({ fallback, alias, onChange }) marks the section named by the address's hash (#messages or
  // #messages/pl_bro_09: the section, then its own parts) with aria-current="true", keeps it in view in the phone row,
  // shows the elements with data-panel="<section>" (hiding the others), and calls onChange(section, rest) now and on
  // every hash change. alias maps a hash to the section the panel marks (e.g. { player: 'find' }). Returns
  // { section(), rest(), go(section, ...rest), count(section, n) }. A page without hash sections (/players/{id}) marks
  // its section in the markup instead.
  function sections(opts = {}) {
    const nav = document.querySelector('nav.views .subviews');
    const links = nav ? [...nav.querySelectorAll('a[data-section]')] : [];
    const names = links.map((a) => a.dataset.section);
    const alias = opts.alias || {};
    const fallback = opts.fallback || names[0] || '';
    let cur = fallback, rest = [];
    const parse = () => {
      const parts = decodeURIComponent(location.hash.replace(/^#/, '')).split('/').filter(Boolean);
      const first = parts[0] || '';
      const known = names.includes(first) || Object.prototype.hasOwnProperty.call(alias, first);
      return known ? [first, parts.slice(1)] : [fallback, []];
    };
    const mark = () => {
      [cur, rest] = parse();
      const shown = alias[cur] || cur;
      for (const a of links) {
        if (a.dataset.section === shown) a.setAttribute('aria-current', 'true'); else a.removeAttribute('aria-current');
      }
      for (const el of document.querySelectorAll('[data-panel]')) el.hidden = el.dataset.panel !== cur;
      const on = nav && nav.querySelector('[aria-current]');
      if (on && nav.scrollWidth > nav.clientWidth) nav.scrollLeft = on.offsetLeft - nav.offsetLeft - 12;  // phone row
      if (typeof opts.onChange === 'function') opts.onChange(cur, rest.slice());
    };
    window.addEventListener('hashchange', mark);
    mark();
    return {
      section: () => cur,
      rest: () => rest.slice(),
      go(section, ...more) { location.hash = [section, ...more].map(encodeURIComponent).join('/'); },
      count(section, n) {
        const el = nav && nav.querySelector(`[data-count="${section}"]`);
        if (el) el.textContent = n ? String(n) : '';
      },
    };
  }

  window.Regista = { esc, reasonLabel, tagLabel, key, api, ApiError, authedObjectUrl, fmtTime, store, sections };
})();
