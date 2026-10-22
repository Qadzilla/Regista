// "Add a match" on a player profile (/players/{global_id}): fills <section id="addMatch"> and nothing else.
// Plain script, no build step, no inline handlers (the CSP allows scripts from this server only).
//
// 1. Add a match: the vision layer's output (events.jsonl + tracks.jsonl) through the token-gated upload (POST /api/matches),
//    or a match already added. On the operator's own machine (the Studio's vision jobs are available) it can also take a
//    video file on that machine and run the vision layer first (a Studio vision-run job); on the live app that part says
//    where video processing runs.
// 2. "Which one is you?": team and kit number in that match, sent as a claim (POST /api/claims). The claim stays pending
//    until the operator confirms it in the Studio; then the match counts in this profile.
//
// Every write needs the admin key, kept as the Studio keeps it: sessionStorage, asked for once, sent only in the
// X-Regista-Token header. Everything from the API reaches the page through textContent, never as markup.
(function () {
  'use strict';
  const root = document.getElementById('addMatch');
  if (!root) return;

  const KEY = 'regista-key';  // the Studio's key slot (shared/regista.js), so a key given in either place works in both
  const key = {
    get() { try { return sessionStorage.getItem(KEY); } catch (e) { return null; } },
    set(v) { try { sessionStorage.setItem(KEY, v); } catch (e) {} },
    clear() { try { sessionStorage.removeItem(KEY); } catch (e) {} },
  };
  const enc = encodeURIComponent;
  const ID = /^[A-Za-z0-9][A-Za-z0-9_.\-]{0,119}$/;
  const NAME = /^[A-Za-z0-9_ .\-]{1,40}$/;
  const gidMatch = /^\/players\/(pl_[a-z0-9_]{1,40})\/?$/.exec(location.pathname);
  if (!gidMatch) return;
  const GID = gidMatch[1];

  // h('p', {class: 'muted'}, 'text', child, ...): elements with text children only; attributes are set, never parsed.
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'style') el.style.cssText = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }
  const clear = (el) => { while (el.firstChild) el.removeChild(el.firstChild); };
  const swap = (el, ...kids) => { clear(el); el.append(...kids.flat().filter(Boolean)); };

  class ApiError extends Error { constructor(status, detail) { super(typeof detail === 'string' ? detail : `HTTP ${status}`); this.status = status; this.detail = detail; } }
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
  function errText(e) {
    const d = e && e.detail !== undefined ? e.detail : e && e.message;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x && x.msg ? x.msg : JSON.stringify(x))).join('; ');
    if (d && d.message) return d.message + (Array.isArray(d.problems) ? `: ${d.problems.slice(0, 5).map(String).join('; ')}` : '');
    return d ? JSON.stringify(d) : String(e);
  }

  // ------------------------------------------------------------------------------------------------ state
  const S = { person: null, writes: null, jobs: false, jobsReason: null, match: null, header: null };
  const canWrite = () => S.writes === 'open' || (S.writes === 'token' && !!key.get());

  const style = 'display:grid;gap:10px';
  const status = h('p', { class: 'muted small', role: 'status', 'aria-live': 'polite' });
  const body = h('div', { style });
  swap(root, h('h2', {}, 'Add a match'),
    h('p', { class: 'muted' }, 'Played in a match Regista has not seen? Add it, then say which player is you. ',
      'The operator confirms the claim in the Studio, and the match then counts in this profile.'),
    body, status);
  const TONE = { ok: 'var(--ok)', bad: 'var(--bad)', warn: 'var(--warn)', muted: 'var(--muted)' };  // shared/regista.css tokens
  const say = (text, cls) => { status.style.color = TONE[cls] || TONE.muted; status.textContent = text || ''; };

  // ------------------------------------------------------------------------------------------------ the key, asked once
  function keyForm(then) {
    const input = h('input', { type: 'password', autocomplete: 'off', placeholder: 'Paste the admin key', 'aria-label': 'Admin key' });
    return h('form', { class: 'panel', style, onsubmit: (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      key.set(v); input.value = '';
      then();
    } },
    h('b', {}, 'Adding a match changes data, so it needs the admin key.'),
    h('span', { class: 'muted small' }, 'The key stays in this tab only (sessionStorage) and travels only in a request header, as in the Studio.'),
    input, h('button', { type: 'submit' }, 'Use this key'));
  }

  async function start() {
    say('');
    try {
      const [person, health] = await Promise.all([api(`/api/players/${enc(GID)}`), api('/api/health')]);
      S.person = person; S.writes = health.writes;
    } catch (e) { say(`Cannot load this player: ${errText(e)}`, 'bad'); return; }
    if (S.writes === 'read-only' || S.writes === 'locked') {
      swap(body, h('p', { class: 'muted' }, S.writes === 'read-only' ? 'This deployment is read-only: matches cannot be added here.'
        : 'This deployment has no admin key configured, so nothing can be added here.'));
      return;
    }
    if (!canWrite()) { swap(body, keyForm(start)); return; }
    // Video needs the vision layer, which runs only where the private models are: the Studio's jobs say whether this is it.
    try {
      const s = await api('/api/studio/session', { auth: true });
      S.jobs = !!(s.capabilities && s.capabilities.jobs);
      S.jobsReason = S.jobs ? null : s.capabilities && s.capabilities.cloud ? 'cloud' : 'models';
    } catch (e) {
      if (e.status === 401) { key.clear(); swap(body, keyForm(start)); say('That key was not accepted.', 'bad'); return; }
      S.jobs = false;
    }
    chooseSource();
  }

  // ------------------------------------------------------------------------------------------------ 1. add a match
  function chooseSource() {
    const p = S.person;
    const intro = h('p', { class: 'small' }, `For ${p.name} (${p.club}, number ${p.kit_number}).`);
    const files = uploadForm();
    const existing = h('div');
    loadExisting(existing);
    const video = S.jobs ? videoForm() : h('p', { class: 'muted small' },
      'Have a video instead? Video processing runs on the operator’s machine, where the vision layer lives: ',
      'it turns footage into events.jsonl and tracks.jsonl, which you add here.',
      S.jobsReason === 'models' ? ' (This Regista has no vision models: python3 -m regista.vision train.)' : '');
    swap(body, intro, files, video, existing);
  }

  function uploadForm() {
    const ev = h('input', { type: 'file', accept: '.jsonl,application/json,text/plain', 'aria-label': 'events.jsonl' });
    const tr = h('input', { type: 'file', accept: '.jsonl,application/json,text/plain', 'aria-label': 'tracks.jsonl' });
    const mid = h('input', { maxlength: 120, placeholder: 'match id (default: from the file)', 'aria-label': 'Match id' });
    const go = h('button', { type: 'submit' }, 'Add the match');
    const form = h('form', { class: 'panel', style, onsubmit: async (e) => {
      e.preventDefault();
      const f = ev.files[0];
      if (!f) { say('Pick events.jsonl first.', 'bad'); return; }
      const id = mid.value.trim();
      if (id && (!ID.test(id) || id.includes('..'))) { say('Match id: letters, digits, _ . - only.', 'bad'); return; }
      const fd = new FormData();
      fd.append('events', f, 'events.jsonl');
      if (tr.files[0]) fd.append('tracks', tr.files[0], 'tracks.jsonl');
      const qs = new URLSearchParams();
      if (id) qs.set('match_id', id);
      go.disabled = true; say('Validating and running the Agent Framework workflow…');
      try {
        const out = await api(`/api/matches${qs.toString() ? `?${qs}` : ''}`, { method: 'POST', body: fd, auth: true });
        say(`Match ${out.match_id} added: ${out.pipeline_ok ? 'the workflow ran' : 'the workflow reported a problem (see the Studio)'}.`, out.pipeline_ok ? 'ok' : 'warn');
        claimStep(out.match_id);
      } catch (err) {
        if (err.status === 401) { key.clear(); swap(body, keyForm(start)); say('That key is no longer accepted.', 'bad'); return; }
        say(errText(err), 'bad');
      } finally { go.disabled = false; }
    } },
    h('b', {}, 'The vision layer’s output'),
    h('label', { class: 'small', style: 'display:grid;gap:4px' }, 'events.jsonl (validated against the schema first)', ev),
    h('label', { class: 'small', style: 'display:grid;gap:4px' }, 'tracks.jsonl (optional: positions, for video)', tr),
    mid, go);
    return form;
  }

  async function loadExisting(el) {
    let all;
    try { all = await api('/api/matches'); } catch (e) { return; }
    const local = (all || []).filter((m) => m.source === 'local' && !/^rl_/.test(m.match_id));
    if (!local.length) return;
    const sel = h('select', { 'aria-label': 'A match already added' }, local.map((m) => h('option', { value: m.match_id },
      `${m.title || m.match_id}${(m.teams || []).length ? ` · ${m.teams.map((t) => t.short_name).join(' v ')}` : ''}`)));
    swap(el, h('form', { class: 'panel', style, onsubmit: (e) => { e.preventDefault(); claimStep(sel.value); } },
      h('b', {}, 'Or a match already added'), sel, h('button', { type: 'submit', class: 'alt' }, 'Find me in this match')));
  }

  function videoForm() {
    const path = h('input', { maxlength: 500, placeholder: '/path/to/match.mp4 on this machine', 'aria-label': 'Video path' });
    const roster = h('select', { 'aria-label': 'Team sheet' }, h('option', { value: '' }, 'loading team sheets…'));
    const out = h('input', { maxlength: 120, placeholder: 'new match id, e.g. vis_0301', 'aria-label': 'New match id' });
    const go = h('button', { type: 'submit' }, 'Run the vision layer');
    api('/api/matches').then((all) => {
      const local = (all || []).filter((m) => m.source === 'local');
      swap(roster, h('option', { value: '' }, 'team sheet: pick a match'), local.map((m) => h('option', { value: m.match_id }, m.title || m.match_id)));
    }).catch(() => {});
    return h('form', { class: 'panel', style, onsubmit: async (e) => {
      e.preventDefault();
      const args = { video: path.value.trim(), roster: roster.value, out: out.value.trim(), workflow: true };
      if (!args.video || !args.roster || !ID.test(args.out)) { say('Give the video path, a team sheet and a new match id.', 'bad'); return; }
      go.disabled = true; say('Starting the vision layer…');
      try {
        const job = await api('/api/studio/jobs', { method: 'POST', body: { kind: 'vision-run', args }, auth: true });
        await follow(job.id, args.out);
      } catch (err) {
        if (err.status === 401) { key.clear(); swap(body, keyForm(start)); say('That key is no longer accepted.', 'bad'); return; }
        say(errText(err), 'bad');
      } finally { go.disabled = false; }
    } },
    h('b', {}, 'A video, on this machine'),
    h('span', { class: 'muted small' }, 'Runs the vision layer here (a Studio job), then asks which player is you.'),
    path, roster, out, go);
  }

  async function follow(jobId, matchId) {
    for (;;) {
      const job = await api(`/api/studio/jobs/${enc(jobId)}`, { auth: true });
      if (job.status === 'running') {
        say(`The vision layer is running (job ${jobId}). This takes a while; the log is in the Studio, Jobs.`);
        await new Promise((r) => setTimeout(r, 3000));
        continue;
      }
      if (job.status !== 'ok') { say(`The vision job ended ${job.status}: see Studio, Jobs, ${jobId}.`, 'bad'); return; }
      say(`The vision layer wrote match ${matchId}.`, 'ok');
      claimStep(matchId);
      return;
    }
  }

  // ------------------------------------------------------------------------------------------------ 2. which one is you?
  async function claimStep(matchId) {
    if (!ID.test(matchId || '')) return;
    let m;
    try { m = await api(`/api/matches/${enc(matchId)}`); } catch (e) { say(errText(e), 'bad'); return; }
    S.match = matchId; S.header = m;
    const p = S.person;
    const teams = m.teams || [];
    const players = m.players || [];
    if (players.some((x) => x.global_player_id)) { say('This match already knows who everyone is: it needs no claim.', 'muted'); return; }
    const team = h('select', { 'aria-label': 'Your team' }, teams.map((t) => h('option', { value: t.team_id }, t.name || t.team_id)));
    const kit = h('select', { 'aria-label': 'Your kit number' });
    const who = h('p', { class: 'small' });
    const name = h('input', { maxlength: 40, placeholder: 'your name (optional)', 'aria-label': 'Your name' });
    const note = h('input', { maxlength: 300, placeholder: 'anything the operator should know (optional)', 'aria-label': 'Note' });
    const go = h('button', { type: 'submit' }, 'That’s me');
    const pick = () => players.find((x) => x.team_id === team.value && String(x.kit_number) === kit.value);
    const fillKits = () => {
      const nums = players.filter((x) => x.team_id === team.value).map((x) => x.kit_number).sort((a, b) => a - b);
      swap(kit, nums.map((n) => h('option', { value: String(n) }, String(n))));
      if (nums.includes(p.kit_number)) kit.value = String(p.kit_number);
      showWho();
    };
    const showWho = () => {
      const x = pick();
      who.textContent = x ? `On this team sheet: ${x.name} (${x.kit_number})${x.kit_number !== p.kit_number ? ` — your profile number is ${p.kit_number}` : ''}.` : '';
    };
    team.addEventListener('change', fillKits);
    kit.addEventListener('change', showWho);
    // Start on the team that has the profile's number, if any.
    const withNumber = teams.find((t) => players.some((x) => x.team_id === t.team_id && x.kit_number === p.kit_number));
    if (withNumber) team.value = withNumber.team_id;
    fillKits();
    swap(body, h('form', { class: 'panel', style, onsubmit: async (e) => {
      e.preventDefault();
      const x = pick();
      if (!x) { say('Pick your team and kit number.', 'bad'); return; }
      const claimant = name.value.trim() || 'claimant';
      if (!NAME.test(claimant)) { say('Name: letters, digits, spaces, . _ - (up to 40).', 'bad'); return; }
      go.disabled = true; say('Sending the claim…');
      try {
        const out = await api('/api/claims', { method: 'POST', auth: true,
          body: { match_id: matchId, player_id: x.player_id, global_id: GID, claimant, note: note.value.trim() } });
        done(out.claim);
      } catch (err) {
        if (err.status === 401) { key.clear(); swap(body, keyForm(start)); say('That key is no longer accepted.', 'bad'); return; }
        say(errText(err), 'bad'); go.disabled = false;
      }
    } },
    h('b', {}, `Which one is you in ${m.title || matchId}?`),
    h('label', { class: 'small', style: 'display:grid;gap:4px' }, 'Team', team),
    h('label', { class: 'small', style: 'display:grid;gap:4px' }, 'Kit number', kit),
    who, name, note,
    h('div', { style: 'display:flex;gap:10px;flex-wrap:wrap' }, go, h('button', { type: 'button', class: 'alt', onclick: chooseSource }, 'Back'))));
  }

  function done(c) {
    swap(body, h('div', { class: 'panel', style },
      h('b', {}, 'Claim sent: pending.'),
      h('span', {}, `${c.player.name || c.player_id} (${c.player.kit_number}) in ${c.match_id} is ${S.person.name}, if the operator confirms it in the Studio. `,
        'Once confirmed, Regista cuts your moments in that match and this profile counts it.'),
      h('span', { class: 'small' }, h('a', { href: c.links.match }, 'Watch the match'), ' · ', h('a', { href: '/studio#claims' }, 'Studio, Claims')),
      h('button', { type: 'button', class: 'alt', onclick: chooseSource }, 'Add another match')));
    say('');
  }

  start();
})();
