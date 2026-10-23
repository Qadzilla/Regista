// The Player view (/me): pick a (synthetic) league player, upload their footage, watch Regista's agents work on it,
// answer "is this you?", and see the moments it cut. Plain script, no build step, no inline handlers (the CSP allows
// scripts from this server only). Everything from the API reaches the page through textContent or attributes set one by
// one, never as markup.
//
// Uploads and answers need the admin key, kept as the Studio keeps it (shared/regista.js: sessionStorage, asked for
// once, sent only in the X-Regista-Token header). Reads are open, so anyone can follow the progress.
(function () {
  'use strict';
  const R = window.Regista;
  const $ = (id) => document.getElementById(id);
  const enc = encodeURIComponent;
  const GID_RE = /^pl_[a-z0-9_]{1,40}$/;
  const POLL_MS = 2000;

  // h('p', {class: 'muted'}, 'text', child, ...): elements with text children only; attributes are set, never parsed.
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else el.setAttribute(k, v === true ? '' : String(v));
    }
    for (const kid of kids.flat()) if (kid !== null && kid !== undefined && kid !== false) el.append(kid instanceof Node ? kid : String(kid));
    return el;
  }
  const swap = (el, ...kids) => { el.replaceChildren(...kids.flat().filter((k) => k !== null && k !== undefined && k !== false)); };

  function errText(e) {
    const d = e && e.detail !== undefined ? e.detail : e && e.message;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) return d.map((x) => (x && x.msg ? x.msg : JSON.stringify(x))).join('; ');
    return d ? JSON.stringify(d) : String(e);
  }
  const colour = (c, fallback) => (typeof c === 'string' && /^#[0-9a-fA-F]{3,8}$/.test(c) ? c : fallback);
  function paintShirt(el, p) {
    const kit = p.kit || {};
    el.textContent = p.kit_number;
    el.style.background = colour(p.position === 'GK' ? kit.gk : kit.primary, '#444');
    el.style.color = p.position === 'GK' ? '#fff' : colour(kit.secondary, '#fff');
  }
  const POS = { GK: 'Goalkeeper', DF: 'Defender', MF: 'Midfielder', FW: 'Forward' };
  function fmtMs(ms) {
    if (typeof ms !== 'number' || !Number.isFinite(ms) || ms <= 0) return '';
    const s = ms / 1000;
    if (s < 10) return `${s.toFixed(1)} s`;
    if (s < 60) return `${Math.round(s)} s`;
    return `${Math.floor(s / 60)} min ${String(Math.round(s % 60)).padStart(2, '0')} s`;
  }
  const fmtClock = (epoch) => {
    try { return new Date(epoch * 1000).toLocaleString([], { weekday: 'short', hour: '2-digit', minute: '2-digit' }); } catch (e) { return ''; }
  };

  // ------------------------------------------------------------------------------------------------ state
  const S = {
    gid: null, person: null, clubs: [], writes: null, maxMb: 300, store: null,
    uploads: new Map(),   // upload_id -> { rec, el, sig, answers: Map(item_id -> bool), results: key loaded }
    timer: null, busy: false,
  };
  const canWrite = () => S.writes === 'open' || (S.writes === 'token' && !!R.key.get());

  function netError(text, retry) {
    $('netErrorText').textContent = text;
    $('netError').hidden = false;
    $('netRetry').onclick = () => { $('netError').hidden = true; retry(); };
  }
  const offline = (e) => !(e instanceof R.ApiError);

  // ------------------------------------------------------------------------------------------------ 1. pick your player
  async function suggest() {
    try {
      const out = await R.api('/api/players?position=FW&sort=goals&limit=6');
      listFound(out.players, 'Or pick one of the league’s forwards:');
    } catch (e) {
      if (offline(e)) netError('Regista cannot be reached. Check the connection.', suggest);
    }
  }

  async function search(q) {
    if (!q) return suggest();
    try {
      const out = await R.api(`/api/players?q=${enc(q)}&sort=name&limit=12`);
      listFound(out.players, out.players.length ? `${out.players.length === 12 ? 'The first 12' : out.players.length} matching “${q}”:` : `No player matches “${q}”.`);
    } catch (e) { $('foundNote').textContent = `Search failed: ${errText(e)}`; }
  }

  function listFound(players, note) {
    $('foundNote').textContent = note;
    swap($('found'), (players || []).map((p) => {
      const mini = h('span', { class: 'mini', 'aria-hidden': 'true' });
      paintShirt(mini, p);
      return h('li', {}, h('button', { type: 'button', onclick: () => choose(p.global_id) }, mini,
        h('span', { class: 'who' }, h('span', { class: 'nm' }, p.name), h('span', { class: 'cl' }, `${p.club} · ${POS[p.position] || p.position} · #${p.kit_number}`))));
    }));
  }

  async function choose(gid, { quiet = false } = {}) {
    if (!GID_RE.test(gid || '')) return;
    let p;
    try { p = await R.api(`/api/players/${enc(gid)}`); } catch (e) {
      if (!quiet) $('foundNote').textContent = `That player could not be loaded: ${errText(e)}`;
      return;
    }
    S.gid = gid; S.person = p;
    const url = new URL(location.href);
    url.searchParams.set('player', gid);
    try { history.replaceState(null, '', url.pathname + url.search); } catch (e) { /* the page still works */ }
    paintShirt($('shirt'), p);
    $('chosenName').textContent = p.name;
    $('chosenLine').textContent = `${p.club} · ${POS[p.position] || p.position} · number ${p.kit_number} · ${p.appearances} match${p.appearances === 1 ? '' : 'es'} in Regista`;
    $('chosenProfile').href = `/players/${enc(gid)}`;
    $('chosen').hidden = false; $('finder').hidden = true;
    $('footage').hidden = false; $('uploads').hidden = false;
    fillOpponents();
    renderKey();
    S.uploads.forEach((u) => u.el.remove());
    S.uploads.clear();
    await refresh();
  }

  function change() {
    $('chosen').hidden = true; $('finder').hidden = false;
    $('footage').hidden = true; $('uploads').hidden = true;
    S.gid = null; S.person = null;
    clearTimeout(S.timer);
    $('find').focus();
  }

  // ------------------------------------------------------------------------------------------------ 2. your footage
  function fillOpponents() {
    const mine = S.person && S.person.club_id;
    swap($('opponent'), S.clubs.filter((c) => c.club_id !== mine).map((c) => h('option', { value: c.club_id }, c.name)));
  }

  function renderKey() {
    const box = $('keyBox');
    const form = $('uploadForm');
    if (S.writes === 'read-only' || S.writes === 'locked') {
      swap(box, h('p', { class: 'msg warn' }, S.writes === 'read-only' ? 'This deployment is read-only: nothing can be uploaded here.'
        : 'This deployment has no admin key configured, so nothing can be uploaded here.'));
      form.hidden = true;
      return;
    }
    form.hidden = false;
    if (canWrite()) {
      swap(box, S.writes === 'token' ? h('p', { class: 'muted small' }, 'Using the admin key from this tab. ',
        h('button', { type: 'button', class: 'alt', onclick: () => { R.key.clear(); renderKey(); } }, 'Forget it')) : null);
      $('uploadGo').disabled = false;
      return;
    }
    const input = h('input', { type: 'password', autocomplete: 'off', placeholder: 'Paste the admin key', 'aria-label': 'Admin key' });
    swap(box, h('form', { class: 'keyform', onsubmit: (e) => {
      e.preventDefault();
      const v = input.value.trim();
      if (!v) return;
      R.key.set(v); input.value = '';
      renderKey();
      say('Key kept for this tab. Pick the video and upload.', 'ok');
    } },
    h('p', {}, h('b', {}, 'The operator’s admin key')),
    h('p', { class: 'muted small' }, 'It stays in this tab only (sessionStorage) and travels only in a request header, as in the Studio.'),
    h('div', { class: 'row' }, input, h('button', { type: 'submit' }, 'Use this key'))));
    $('uploadGo').disabled = true;
  }

  function say(text, tone) {
    const m = $('uploadMsg');
    m.className = `msg ${tone || ''}`;
    m.textContent = text || '';
  }

  // XMLHttpRequest, not fetch: it reports how much of the video has gone up.
  function send(fd, onProgress) {
    return new Promise((resolve, reject) => {
      const x = new XMLHttpRequest();
      x.open('POST', '/api/player/uploads');
      if (R.key.get()) x.setRequestHeader('X-Regista-Token', R.key.get());
      x.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded, e.total); };
      x.onload = () => {
        let data = x.responseText;
        try { data = data ? JSON.parse(data) : null; } catch (e) { /* text */ }
        if (x.status >= 200 && x.status < 300) resolve(data);
        else reject(new R.ApiError(x.status, data && data.detail !== undefined ? data.detail : data));
      };
      x.onerror = () => reject(new Error('the connection dropped during the upload'));
      x.send(fd);
    });
  }

  async function upload(e) {
    e.preventDefault();
    const f = $('video').files[0];
    if (!f) { say('Pick the video first.', 'bad'); return; }
    if (!/\.mp4$/i.test(f.name)) { say('The footage must be an MP4 file (.mp4).', 'bad'); return; }
    if (f.size > S.maxMb * 1024 * 1024) { say(`That video is ${(f.size / 1048576).toFixed(0)} MB; the limit is ${S.maxMb} MB.`, 'bad'); return; }
    if (!$('opponent').value) { say('Pick the club you played against.', 'bad'); return; }
    const side = (document.querySelector('input[name="side"]:checked') || {}).value || 'home';
    const fd = new FormData();
    fd.append('global_id', S.gid);
    fd.append('opponent_club_id', $('opponent').value);
    fd.append('side', side);
    fd.append('video', f, f.name);
    $('uploadGo').disabled = true; say('');
    $('sending').hidden = false;
    const bar = $('sendBar');
    const progress = (done, total) => {
      const pct = Math.round((100 * done) / Math.max(1, total));
      bar.style.width = `${pct}%`;
      $('sendBarWrap').setAttribute('aria-valuenow', String(pct));
      $('sendText').textContent = pct < 100 ? `Uploading ${(done / 1048576).toFixed(1)} of ${(total / 1048576).toFixed(1)} MB…`
        : 'Storing the video and queueing the vision job…';
    };
    progress(0, f.size);
    try {
      const out = await send(fd, progress);
      say(`Uploaded. The vision job is queued${out.store === 'azure' ? ' in Azure' : ''}: follow it below.`, 'ok');
      $('uploadForm').reset();
      upsert(out.upload);
      order();
      schedule(300);
      const u = S.uploads.get(out.upload.upload_id);
      if (u) u.el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    } catch (err) {
      if (err.status === 401) { R.key.clear(); renderKey(); say('That key was not accepted. Paste it again.', 'bad'); }
      else if (err.status === 403) say(errText(err), 'bad');
      else say(`The upload failed: ${errText(err)}`, 'bad');
    } finally {
      $('sending').hidden = true;
      $('uploadGo').disabled = !canWrite();
    }
  }

  // ------------------------------------------------------------------------------------------------ 3. Regista at work
  // The agents in the order they run. A stage's role (from the worker's record) lights its step; the intelligence
  // roles after the vision workflow all count as "Clips". "Is this you?" shows only when the player is asked.
  const STEPS = [
    { key: 'queued', label: 'Queued', roles: ['queued'], what: 'The video is stored and the job waits on the vision-jobs queue for a worker.' },
    { key: 'shots', label: 'Shots', roles: ['shots'], what: 'Cuts the feed into camera shots: the main view, replays, highlights and closeups.' },
    { key: 'identity', label: 'Identity', roles: ['identity'], what: 'Finds every player and names them by kit number, team colours and tracking.' },
    { key: 'review', label: 'Is this you?', roles: ['identity_review'], optional: true, what: 'Asks you about the calls it is least sure of.' },
    { key: 'possession', label: 'Possession', roles: ['possession_vision'], what: 'Decides who is on the ball, moment by moment.' },
    { key: 'events', label: 'Events', roles: ['events_vision'], what: 'Spots passes, shots, take-ons, nutmegs and tackles.' },
    { key: 'writer', label: 'Writer', roles: ['vision_writer'], what: 'Writes the match as Regista’s event stream.' },
    { key: 'clips', label: 'Clips', roles: ['ingest', 'validator', 'possession', 'clip', 'clips', 'label', 'recap', 'persist', 'indexer', 'profiles', 'profile'],
      what: 'Cuts every moment you are on the ball, plus your replays, and labels them.' },
    { key: 'done', label: 'Done', roles: [], what: 'The match is in your profile.' },
  ];
  const OK = new Set(['ok', 'done', 'completed', 'success', 'succeeded']);
  const RUN = new Set(['running', 'started', 'working', 'retry', 'retrying']);
  const FAIL = new Set(['failed', 'error', 'dead_letter', 'dead']);
  const SKIP = new Set(['skipped', 'skip']);
  const STATUS = { queued: 'Queued', running: 'Working', needs_review: 'Is this you?', done: 'Done', failed: 'Failed' };

  function asked(rec) {
    return rec.status === 'needs_review' || (rec.stages || []).some((s) => s.role === 'identity_review' && /answer/i.test(s.note || ''));
  }

  function steps(rec) {
    const stages = Array.isArray(rec.stages) ? rec.stages : [];
    const shown = STEPS.filter((st) => !st.optional || asked(rec));
    const rows = shown.map((st) => {
      const ss = stages.filter((s) => st.roles.includes(s.role));
      const ms = ss.reduce((t, s) => t + (typeof s.ms === 'number' ? s.ms : 0), 0);
      const note = ss.map((s) => s.note).filter(Boolean).slice(-1)[0] || '';
      let state = 'pending';
      if (st.key === 'done') state = rec.status === 'done' ? 'ok' : 'pending';
      else if (st.key === 'review') state = rec.status === 'needs_review' ? 'ask' : 'ok';
      else if (st.key === 'queued') state = rec.status === 'queued' ? 'running' : 'ok';
      else if (ss.some((s) => FAIL.has(s.status))) state = 'failed';
      else if (ss.some((s) => RUN.has(s.status))) state = 'running';
      else if (ss.length && ss.every((s) => SKIP.has(s.status))) state = 'skipped';
      else if (ss.length) state = 'ok';
      return { ...st, state, ms, note };
    });
    const last = rows.map((r) => r.state !== 'pending').lastIndexOf(true);
    if (rec.status === 'running' && !rows.some((r) => r.state === 'running')) {
      const next = rows.findIndex((r, i) => i > last && r.state === 'pending');
      if (next >= 0) rows[next].state = 'running';
    }
    if (rec.status === 'failed' && !rows.some((r) => r.state === 'failed')) {
      const next = rows.findIndex((r, i) => i > last && r.state === 'pending');
      if (next >= 0) rows[next].state = 'failed';
    }
    if (rec.status === 'done' || rec.status === 'needs_review') {
      rows.forEach((r, i) => { if (r.state === 'pending' && r.key !== 'done' && (rec.status === 'done' || i < rows.findIndex((x) => x.key === 'review'))) r.state = 'ok'; });
    }
    return rows;
  }

  const ICON = { ok: '✓', failed: '✕', ask: '?', skipped: '–', pending: '', running: '' };

  function pipeline(rec) {
    const rows = steps(rec);
    const ol = h('ol', { class: 'pipe', 'aria-label': 'Regista’s agents on this video' });
    ol.style.setProperty('--n', String(rows.length));
    for (const r of rows) {
      const time = r.state === 'running' ? (r.key === 'queued' ? 'waiting…' : 'working…') : r.state === 'ask' ? 'your turn' : fmtMs(r.ms);
      ol.append(h('li', { class: r.state, title: `${r.label}: ${r.what}${r.note ? ` (${r.note})` : ''}` },
        h('span', { class: 'node', 'aria-hidden': 'true' }, ICON[r.state] || ''),
        h('span', { class: 'lbl' }, r.label),
        h('span', { class: 'tm' }, time),
        h('span', { class: 'sr' }, ` ${({ ok: 'done', running: 'working', ask: 'waiting for you', failed: 'failed', skipped: 'skipped', pending: 'not yet' })[r.state]}`)));
    }
    const now = rows.find((r) => r.state === 'running' || r.state === 'ask' || r.state === 'failed');
    const total = (rec.stages || []).reduce((t, s) => t + (typeof s.ms === 'number' ? s.ms : 0), 0);
    let line = null;
    if (now && now.state === 'running' && now.key === 'queued') {
      line = h('p', { class: 'now' }, h('b', {}, 'Waiting for a worker'),
        h('span', {}, S.store === 'azure' ? 'The video is in Azure Blob Storage; an Azure Container Apps Job picks the job up from the queue.' : now.what));
    } else if (now && now.state === 'running') line = h('p', { class: 'now' }, h('b', {}, `${now.label} agent`), h('span', {}, now.what));
    else if (rec.status === 'done') line = h('p', { class: 'now' }, h('b', {}, 'Finished'), h('span', { class: 'muted' }, total ? `The agents took ${fmtMs(total)} in all.` : 'Every agent has run.'));
    return [ol, line];
  }

  function title(rec) {
    const opp = rec.opponent ? rec.opponent.name : rec.opponent_club_id;
    return `${rec.side === 'away' ? 'At' : 'Against'} ${opp} · ${rec.side === 'away' ? 'away' : 'home'}`;
  }

  // One card per upload, kept across polls: only the parts whose data changed are rebuilt, so a playing clip or an
  // answer in progress is never reset by the next poll.
  function upsert(rec) {
    let u = S.uploads.get(rec.upload_id);
    if (!u) {
      const el = h('li', { class: 'run' });
      u = { rec, el, sig: '', answers: new Map(), parts: {}, results: null, questions: null };
      el.append(u.parts.head = h('div', { class: 'run-head' }), u.parts.pipe = h('div', { class: 'pipe-wrap' }),
        u.parts.err = h('p', { class: 'err', role: 'alert' }), u.parts.ask = h('div', { class: 'ask-block' }), u.parts.res = h('div', { class: 'results' }));
      S.uploads.set(rec.upload_id, u);
      $('runs').append(el);
    }
    u.rec = rec;
    const sig = JSON.stringify([rec.status, rec.stages, rec.error, rec.updated_at, !!rec.links]);
    if (sig === u.sig) return;
    u.sig = sig;
    u.el.classList.toggle('live', rec.status === 'queued' || rec.status === 'running');
    swap(u.parts.head, h('div', {},
      h('p', { class: 'run-title' }, title(rec)),
      h('p', { class: 'run-sub' }, [fmtClock(rec.created_at), rec.size_bytes ? `${(rec.size_bytes / 1048576).toFixed(1)} MB` : null,
        rec.source === 'synthetic' ? 'synthetic footage' : null].filter(Boolean).join(' · '))),
    h('span', { class: `pill ${rec.status}` }, STATUS[rec.status] || rec.status));
    swap(u.parts.pipe, pipeline(rec));
    u.parts.err.textContent = rec.status === 'failed' ? `The job stopped: ${rec.error || 'no reason given'}` : '';
    u.parts.err.hidden = rec.status !== 'failed';
    if (rec.status === 'needs_review') loadQuestions(u); else { swap(u.parts.ask); u.questions = null; }
    if (rec.status === 'done' && rec.links) loadResults(u); else if (rec.status !== 'done') { swap(u.parts.res); u.results = null; }
  }

  function order() {
    const runs = [...S.uploads.values()].sort((a, b) => b.rec.created_at - a.rec.created_at);
    for (const u of runs) $('runs').append(u.el);
    $('noUploads').hidden = runs.length > 0;
    const live = runs.filter((u) => u.rec.status === 'queued' || u.rec.status === 'running').length;
    $('uploadsSub').textContent = runs.length ? `${runs.length} upload${runs.length === 1 ? '' : 's'}${live ? ` · ${live} in progress, updating live` : ''}` : '';
  }

  async function refresh() {
    if (!S.gid || S.busy) return;
    S.busy = true;
    const gid = S.gid;
    try {
      const out = await R.api(`/api/player/uploads?global_id=${enc(gid)}`);
      if (gid !== S.gid) return;
      if (out.max_mb) { S.maxMb = out.max_mb; $('maxMb').textContent = String(out.max_mb); }
      S.store = out.store || null;
      $('netError').hidden = true;
      for (const rec of out.uploads || []) upsert(rec);
      order();
    } catch (e) {
      if (offline(e)) netError('Regista cannot be reached; progress will update when it is back.', refresh);
    } finally {
      S.busy = false;
      const active = [...S.uploads.values()].some((u) => u.rec.status === 'queued' || u.rec.status === 'running');
      if (S.gid === gid) schedule(active ? POLL_MS : 15000);
    }
  }

  // The working agent's clock, counted from the record's last change (the worker writes it when a stage starts).
  function tick() {
    const now = Date.now() / 1000;
    for (const u of S.uploads.values()) {
      if (u.rec.status !== 'queued' && u.rec.status !== 'running') continue;
      const tm = u.el.querySelector('.pipe li.running .tm');
      if (!tm) continue;
      const secs = Math.max(0, Math.round(now - (u.rec.updated_at || now)));
      tm.textContent = `${u.rec.status === 'queued' ? 'waiting' : 'working'} ${R.fmtTime(secs)}`;
    }
  }

  function schedule(ms) {
    clearTimeout(S.timer);
    S.timer = setTimeout(() => { if (document.hidden) schedule(ms); else refresh(); }, ms);
  }

  // ------------------------------------------------------------------------------------------------ "is this you?"
  async function loadQuestions(u) {
    if (u.questions && u.questions.upload === u.rec.updated_at) return;
    u.questions = { upload: u.rec.updated_at };
    let q;
    try { q = await R.api(`/api/player/uploads/${enc(u.rec.upload_id)}/questions`); } catch (e) {
      swap(u.parts.ask, h('p', { class: 'bad' }, `The questions could not be loaded: ${errText(e)}`));
      return;
    }
    const items = q.items || [];
    const name = S.person ? S.person.name.split(' ')[0] : 'you';
    const status = h('p', { class: 'small', role: 'status', 'aria-live': 'polite' });
    const go = h('button', { type: 'button' }, items.length ? 'Send my answers' : 'Finish');
    const skip = items.length ? h('button', { type: 'button', class: 'alt' }, 'Skip: keep the agents’ calls') : null;
    const cards = items.map((it) => question(u, it));
    const submit = async (all) => {
      if (!canWrite()) { status.className = 'small warn'; status.textContent = 'Answering needs the admin key: paste it in “Your footage” above.'; renderKey(); return; }
      const answers = all ? [...u.answers.entries()].map(([item_id, is_me]) => ({ item_id, is_me })) : [];
      if (all && items.length && !answers.length) { status.className = 'small warn'; status.textContent = 'Answer at least one, or skip.'; return; }
      go.disabled = true; if (skip) skip.disabled = true;
      status.className = 'small';
      status.textContent = answers.length ? 'Applying your answers: identity is corrected, then possession, events and your clips are worked out again…'
        : 'Finishing the match…';
      try {
        const out = await R.api(`/api/player/uploads/${enc(u.rec.upload_id)}/answers`, { method: 'POST', body: { answers }, auth: true });
        status.className = 'small ok';
        status.textContent = answers.length ? `Thanks: ${out.answers} answer${out.answers === 1 ? '' : 's'} applied.` : 'Done.';
        upsert(out.upload); order();
      } catch (e) {
        if (e.status === 401) { R.key.clear(); renderKey(); }
        status.className = 'small bad'; status.textContent = errText(e);
        go.disabled = false; if (skip) skip.disabled = false;
      }
    };
    go.addEventListener('click', () => submit(true));
    if (skip) skip.addEventListener('click', () => submit(false));
    swap(u.parts.ask,
      h('h3', {}, items.length ? `Is this you, ${name}?` : 'Nothing to ask you'),
      h('p', {}, items.length ? `The identity agent is unsure about ${items.length === 1 ? 'one call' : `${items.length} calls`} that may be you. `
        + 'Your answers fix this match now and teach the kit-number reader for the next one.'
        : 'The identity agent had questions about other players, none about you. Finish to add the match to your profile.'),
      items.length ? h('ul', { class: 'qs' }, cards) : null,
      h('div', { class: 'ask-actions' }, go, skip, status));
  }

  function question(u, it) {
    const card = h('li', { class: 'q' });
    const pic = h('div', { class: 'pic' });
    if (it.image_url && /^\/api\/player\/uploads\/[A-Za-z0-9_]+\/crops\/[A-Za-z0-9_.\-]+\.jpg$/.test(it.image_url)) {
      pic.append(h('img', { src: it.image_url, alt: `The ${it.kind === 'track' ? 'player' : it.segment_kind || 'replay'} Regista is asking about, at ${R.fmtTime(it.t || 0)}`, loading: 'lazy' }));
    } else pic.append(`No picture · ${R.fmtTime(it.t || 0)}`);
    const yes = h('button', { type: 'button', class: 'y', 'aria-pressed': 'false' }, 'Yes, me');
    const no = h('button', { type: 'button', class: 'n', 'aria-pressed': 'false' }, 'No');
    const pick = (v) => {
      u.answers.set(it.item_id, v);
      yes.setAttribute('aria-pressed', String(v)); no.setAttribute('aria-pressed', String(!v));
      card.classList.toggle('yes', v); card.classList.toggle('no', !v);
    };
    if (u.answers.has(it.item_id)) setTimeout(() => pick(u.answers.get(it.item_id)));
    yes.addEventListener('click', () => pick(true));
    no.addEventListener('click', () => pick(false));
    const span = it.t0 !== undefined && it.t1 !== undefined ? `${R.fmtTime(it.t0)}–${R.fmtTime(it.t1)}` : R.fmtTime(it.t || 0);
    const pct = typeof it.p === 'number' ? Math.round(it.p * 100) : null;
    const hint = it.regista_thinks_its_you ? 'Regista named you here, but is not sure.'
      : it.kind === 'track' ? `${it.named_as ? `Regista named this player ${it.named_as}` : 'Regista left this player unnamed'}${pct !== null ? `; ${pct}% of its kit-number reads say you.` : '.'}`
      : (pct !== null ? `Regista’s estimate that you are in it: ${pct}%.` : 'Regista is not sure.');
    card.append(pic, h('div', { class: 'qb' },
      h('p', { class: 'qq' }, it.question || 'Is this you?'),
      h('p', { class: 'qm' }, `${it.kind === 'track' ? 'Main camera' : (it.segment_kind ? R.reasonLabel(`${it.segment_kind}_appearance`) : 'Replay')} · ${span}. ${hint}`),
      h('div', { class: 'yn', role: 'group', 'aria-label': it.question || 'Is this you?' }, yes, no)));
    return card;
  }

  // ------------------------------------------------------------------------------------------------ results
  async function loadResults(u) {
    const key = `${u.rec.upload_id}:${u.rec.updated_at}`;
    if (u.results === key) return;
    u.results = key;
    const links = u.rec.links || {};
    let clips = [];
    try { clips = await R.api(links.clips); } catch (e) {
      swap(u.parts.res, h('p', { class: 'bad' }, `The moments could not be loaded: ${errText(e)}`));
      return;
    }
    const pid = u.rec.match && u.rec.match.player_id;
    const mine = (clips || []).filter((c) => !pid || c.player_id === pid);
    const best = mine.slice(0, 6);
    const href = (v) => (typeof v === 'string' && v.startsWith('/') && !v.startsWith('//') ? v : '#');
    swap(u.parts.res,
      h('div', { class: 'section-bar' }, h('h3', {}, `Your moments: ${mine.length}`),
        h('span', { class: 'badge filmed' }, 'Filmed by the player · cut from video')),
      h('p', { class: 'muted small' }, mine.length ? `Best first. ${mine.length > best.length ? `The best ${best.length} are here, and every one is in the Clip view. ` : 'Each one opens in the Clip view too. '}The match now counts in your profile.`
        : 'Regista found no moments of you on the ball in this footage. The match still counts in your profile.'),
      best.length ? h('div', { class: 'moments' }, best.map(moment)) : null,
      h('div', { class: 'links' },
        h('a', { class: 'btn solid', href: href(links.clip_view) }, 'Open the match on Home'),
        h('a', { class: 'btn alt', href: href(links.profile) }, 'See your updated profile')));
    const mid = u.rec.match && u.rec.match.match_id;
    if (mid && pid) {
      const box = h('section', { class: 'recap', 'aria-label': 'Your match recap' }, h('p', { class: 'muted small' }, 'Writing your match recap…'));
      u.parts.res.append(box);
      loadRecap(box, mid, pid, href(links.clip_view));
    }
  }

  // "Your match recap": the match told from the player's side (GET /recap, the Instant engine). Every sentence opens its
  // moment in the Clip view; the recap reel plays here.
  async function loadRecap(box, mid, pid, clipView) {
    let r;
    try { r = await R.api(`/api/matches/${enc(mid)}/recap?player=${enc(pid)}`); } catch (e) {
      swap(box, h('p', { class: 'muted small' }, `The recap could not be written: ${errText(e)}`));
      return;
    }
    const at = (s) => (s.cites || []).find((c) => c.clip_id);
    const sentence = (s) => {
      const c = at(s);
      return c ? h('a', { href: `/?match=${enc(mid)}&player=${enc(c.player_id || pid)}&clip=${enc(c.clip_id)}` }, s.text) : h('span', {}, s.text);
    };
    const reelUrl = typeof r.reel_url === 'string' && r.reel_url.startsWith('/api/matches/') ? r.reel_url : null;
    const video = h('video', { controls: true, playsinline: true, preload: 'none' });
    video.hidden = true;
    const play = reelUrl ? h('button', { type: 'button', class: 'alt' }, `Play your recap reel (${r.reel.length})`) : null;
    if (play) {
      play.addEventListener('click', () => {
        play.textContent = 'Cutting the reel… the first view takes a little while';
        play.disabled = true;
        video.src = reelUrl;
        video.hidden = false;
        video.addEventListener('playing', () => play.remove(), { once: true });
        video.addEventListener('error', () => { play.textContent = 'The reel could not be played. Try again.'; play.disabled = false; }, { once: true });
        video.play().catch(() => {});
      });
    }
    swap(box,
      h('h3', {}, 'Your match recap'),
      h('p', { class: 'headline' }, r.headline || ''),
      (r.paragraphs || []).map((p) => h('p', {}, (p.sentences || []).flatMap((s, i) => (i ? [' ', sentence(s)] : [sentence(s)])))),
      h('p', { class: 'muted small' }, 'Written by Regista from the match events. Each sentence opens its moment in the Clip view.'),
      video,
      h('div', { class: 'links' }, play, h('a', { class: 'btn alt', href: clipView === '#' ? '#' : `${clipView}&recap=1` }, 'Read it on Home')));
  }

  function moment(c) {
    const lb = c.label || {};
    const video = h('video', { controls: true, playsinline: true, preload: 'none' });
    video.hidden = true;
    const wait = h('span', { class: 'wait' }, `${R.reasonLabel(c.reason)} · ${R.fmtTime(c.t)}`);
    const cover = h('button', { type: 'button', class: 'cover', 'aria-label': `Play: ${lb.title || 'moment'}` },
      h('span', { class: 'play', 'aria-hidden': 'true' }, '▶'), wait);
    cover.addEventListener('click', () => {
      if (typeof c.video_url !== 'string' || !c.video_url.startsWith('/api/matches/')) return;
      wait.textContent = 'Cutting the clip…';
      video.src = c.video_url;
      video.hidden = false;
      video.addEventListener('playing', () => cover.remove(), { once: true });
      video.addEventListener('error', () => { wait.textContent = 'The clip could not be played. Try again.'; video.hidden = true; }, { once: true });
      video.play().catch(() => {});
    });
    const tags = (lb.tags || []).filter((t) => t !== 'touch' && t !== 'on_ball_main').slice(0, 4);
    return h('article', { class: 'card' },
      h('div', { class: 'thumb' }, video, cover),
      h('div', { class: 'body' },
        h('p', { class: 't' }, lb.title || 'A moment'),
        h('p', { class: 'm' }, `${R.fmtTime(c.t)} · ${R.reasonLabel(c.reason)}${typeof lb.watchability === 'number' ? ` · worth watching ${Math.round(lb.watchability * 100)}%` : ''}`),
        tags.length ? h('div', { class: 'tags' }, tags.map((t) => h('span', { class: 'tag' }, R.tagLabel(t)))) : null));
  }

  // ------------------------------------------------------------------------------------------------ start
  function wire() {
    setInterval(tick, 1000);
    $('change').addEventListener('click', change);
    $('findForm').addEventListener('submit', (e) => { e.preventDefault(); search($('find').value.trim()); });
    $('uploadForm').addEventListener('submit', upload);
    document.addEventListener('visibilitychange', () => { if (!document.hidden && S.gid) schedule(50); });
  }

  async function start() {
    try {
      const [health, season] = await Promise.all([R.api('/api/health'), R.api('/api/season')]);
      S.writes = health.writes;
      S.clubs = season.clubs || [];
    } catch (e) {
      if (offline(e)) return netError('Regista cannot be reached. Check the connection.', start);
      return netError(`Regista could not load the league: ${errText(e)}`, start);
    }
    const wanted = new URLSearchParams(location.search).get('player');
    if (wanted && GID_RE.test(wanted)) await choose(wanted, { quiet: true });
    if (!S.gid) suggest();
  }

  wire();
  start();
})();
