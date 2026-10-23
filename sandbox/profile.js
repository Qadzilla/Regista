// The Player profile view: Femi Toure's own view of the profile scouts see, plus the owner's tools (Add a match, Your
// uploads). profile.json holds his real profile and upload, read from the live app on 2026-10-23
// (GET /api/players/pl_bro_09 and /api/player/uploads?global_id=pl_bro_09). Clips play from the live app.
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fmtTime = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, '0')}`;
  const INTERNAL = /_appearance$|_against$|^(on_ball_main|touch|possession_change|kick_off|period_start|period_end)$/;
  const REASONS = { on_ball_main: 'On the ball', replay_appearance: 'Replay', highlight_appearance: 'Highlight', closeup_appearance: 'Closeup' };
  const TAGS = { take_on: 'Take-on', key_pass: 'Key pass', ball_won: 'Ball won', skill_move: 'Skill move' };
  const tagLabel = (t) => TAGS[t] || (s => s.charAt(0).toUpperCase() + s.slice(1))(String(t).replace(/_/g, ' '));
  const POS = { FW: 'Forward', MF: 'Midfielder', DF: 'Defender', GK: 'Goalkeeper' };
  const HEADLINE = ['goals', 'assists', 'shots', 'key_passes', 'take_ons_won', 'nutmegs'];
  const STAGES = { download: 'Footage received', shots: 'Camera shots', identity: 'Who is who', identity_review: 'Is this you?',
                   possession_vision: 'On the ball', events_vision: 'Events', vision_writer: 'Match written', clips: 'Clips cut', publish: 'Saved' };

  let P = null, U = [], APP = '', reel = null;
  const clipOf = new Map();  // clip id -> moment

  fetch('profile.json').then(r => r.json()).then(d => {
    P = d.profile; U = d.uploads || []; APP = d.app;
    for (const m of P.moments) clipOf.set(m.clip_id, m);
    paint();
  });

  const roundName = (m) => m.round ? `Round ${m.round}` : 'Friendly';
  const matchOf = (id) => P.matches.find(m => m.match_id === id);
  const vsLine = (m) => {
    if (!m) return '';
    const us = P.club, them = m.opponent;
    if (!m.score) return `${m.home ? us : them} v ${m.home ? them : us}`;
    return m.home ? `${us} ${m.score} ${them}` : `${them} ${m.score} ${us}`;
  };

  function paint() {
    // Header: the shirt in the club's colours with his number, who he is, how much he has played.
    $('pfShirt').innerHTML = `<svg viewBox="0 0 64 60" width="72" height="68"><path d="M20 4 L8 10 L2 24 L11 28 L14 22 L14 56 L50 56 L50 22 L53 28 L62 24 L56 10 L44 4 C42 9 37 12 32 12 C27 12 22 9 20 4 Z" fill="${esc(P.kit.primary)}" stroke="rgba(255,255,255,.25)" stroke-width="1"/>`
      + `<text x="32" y="44" text-anchor="middle" font-size="22" font-weight="800" fill="${esc(P.kit.secondary)}" font-family="-apple-system, Helvetica, Arial, sans-serif">${esc(P.kit_number)}</text></svg>`;
    $('pfName').textContent = P.name;
    $('pfLine').textContent = `${POS[P.position] || P.position} · ${P.club} · Number ${P.kit_number}`;
    $('pfApps').textContent = `${P.appearances} matches · ${Math.round(P.minutes)} minutes`;
    // Add a match: the clubs he can have played (every other league club).
    const opps = [...new Set(P.matches.map(m => m.opponent))].sort();
    $('pfOpp').innerHTML = opps.map(o => `<option>${esc(o)}</option>`).join('');

    paintSummary();
    paintStrip();
    play(best()[0].clip_id, false);
    paintNumbers();
    paintPitch();
    paintMatches();
    paintUploads();
  }

  // ---- summary: each sentence points at what it came from (a number opens its moments, a moment plays)
  function paintSummary() {
    const S = new Map((P.summary.sources || []).map(s => [s.id, s]));
    $('pfSummary').innerHTML = P.summary.sentences.map((x, i) => {
      const src = (x.sources || []).map(id => S.get(id)).filter(Boolean)[0];
      if (!src) return `<span>${esc(x.text)}</span>`;
      const data = src.type === 'moment' ? `data-clip="${esc(src.clip_id)}"` : `data-stat="${esc(src.key)}"`;
      return `<a href="#profile" class="cite" ${data}>${esc(x.text)}</a>`;
    }).join(' ');
    const by = String(P.summary.model || '');
    $('pfSumBy').textContent = by.startsWith('foundry') ? `Written by Microsoft Foundry from his numbers.` : 'Written by Regista from his numbers. Pick a sentence to see where it comes from.';
  }

  // ---- best moments: the best of his clips, on the ball first; one plays on the stage
  function best() {
    const seen = new Set();
    return [...P.moments].sort((a, b) => (b.watchability - a.watchability) || ((a.reason !== 'on_ball_main') - (b.reason !== 'on_ball_main')))
      .filter(m => !seen.has(m.clip_id) && seen.add(m.clip_id)).slice(0, 8);
  }
  function paintStrip() {
    $('pfStrip').innerHTML = best().map(m => `<li><button type="button" class="pf-clip" data-clip="${esc(m.clip_id)}">
      <span class="reason ${m.reason === 'replay_appearance' ? 'replay' : ''}">${esc(REASONS[m.reason] || m.reason)} · ${esc(roundName(m))}</span>
      <span class="pf-ctitle">${esc(m.title.replace(/^.*?: /, ''))}</span>
      <span class="pf-cmatch">${esc(vsLine(matchOf(m.match_id)))}</span></button></li>`).join('');
  }
  function play(clipId, start = true) {
    const m = clipOf.get(clipId);
    if (!m) return;
    const v = $('pfVideo');
    const src = APP + m.video_url;
    if (v.getAttribute('src') !== src) { v.src = src; v.preload = start ? 'auto' : 'none'; }
    $('pfNow').className = 'reason' + (m.reason === 'replay_appearance' ? ' replay' : '');
    $('pfNow').textContent = `${reel ? `Reel · clip ${reel.i} of ${reel.ids.length} · ` : ''}${REASONS[m.reason] || m.reason} · ${roundName(m)} · ${fmtTime(m.t)}`;
    $('pfTitle').textContent = m.title.replace(/^.*?: /, '');
    $('pfTags').innerHTML = (m.tags || []).filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
    for (const b of document.querySelectorAll('.pf-clip')) b.classList.toggle('on', b.dataset.clip === clipId);
    if (start) { v.play().catch(() => {}); $('pfVideo').closest('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
  }
  $('pfReel').onclick = () => { reel = { ids: best().map(m => m.clip_id), i: 1 }; play(reel.ids[0]); };
  $('pfVideo').addEventListener('ended', () => {
    if (!reel) return;
    if (reel.i >= reel.ids.length) { reel = null; return; }
    reel.i++; play(reel.ids[reel.i - 1]);
  });

  // ---- numbers: the headline counts, each with its rate and where it ranks; a tile opens the moments behind it
  const pctText = (p) => p >= 100 ? 'Best of the league\'s forwards' : `Higher than ${p}% of the league's forwards`;
  function paintNumbers() {
    $('pfTiles').innerHTML = HEADLINE.map(k => `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="false">
      <span class="pf-n">${esc(P.counts[k])}</span><span class="pf-k">${esc(P.stat_labels[k] || k)}</span>
      <span class="pf-rate">${esc(P.per90[k].toFixed(2))} per 90 minutes</span>
      <span class="pf-pbar" title="${esc(pctText(P.percentiles[k]))}"><i style="width:${Math.max(3, P.percentiles[k])}%"></i></span>
      <span class="pf-pct">${esc(pctText(P.percentiles[k]))}</span></button>`).join('');
    const r = P.ratios;
    $('pfRatios').innerHTML = [['Passes completed', r.pass_accuracy], ['Shots on target', r.shot_accuracy], ['Take-ons won', r.take_on_success]]
      .map(([k, v]) => `<span><b>${esc(Math.round(v * 100))}%</b> ${esc(k.toLowerCase())}</span>`).join('');
  }
  // toggle: a tile opens and closes its moments; a summary sentence only ever opens them.
  function openStat(key, toggle = true) {
    const box = $('pfEvidence');
    const closing = toggle && box.dataset.stat === key && !box.hidden;
    for (const t of document.querySelectorAll('.pf-tile')) t.setAttribute('aria-pressed', String(t.dataset.stat === key && !closing));
    if (closing) { box.hidden = true; box.dataset.stat = ''; return; }
    const ev = P.evidence[key] || [];
    box.dataset.stat = key; box.hidden = false;
    const label = (P.stat_labels[key] || key).toLowerCase();
    box.innerHTML = `<h3>${esc(P.counts[key])} ${esc(label)}, verified by Regista</h3><ol>${ev.map(e => {
      const m = matchOf(e.match_id), c = e.clip_id && clipOf.get(e.clip_id);
      const where = `${roundName(m || {})} · ${vsLine(m)} · ${fmtTime(e.t)}`;
      return c ? `<li><button type="button" class="link" data-clip="${esc(e.clip_id)}">${esc(c.title.replace(/^.*?: /, ''))}</button> <span class="muted">${esc(where)}</span></li>`
        : `<li><span>${esc(where)}</span> <span class="muted">· in the match, no clip of its own</span></li>`;
    }).join('')}</ol>`;
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ---- where he plays: his touches over the season on a 12 x 8 grid, attacking left to right
  function paintPitch() {
    const g = P.grid, max = Math.max(1, ...g.flat());
    const cells = g.map((row, y) => row.map((n, x) => `<i style="grid-row:${y + 1};grid-column:${x + 1};opacity:${n ? (0.12 + 0.88 * n / max).toFixed(2) : 0}" title="${n} touches"></i>`).join('')).join('');
    $('pfPitch').innerHTML = `<div class="heat">${cells}</div><svg viewBox="0 0 120 80" preserveAspectRatio="none" aria-hidden="true">
      <rect x="0.5" y="0.5" width="119" height="79"/><line x1="60" y1="0" x2="60" y2="80"/><circle cx="60" cy="40" r="9"/>
      <rect x="0.5" y="22" width="16" height="36"/><rect x="103.5" y="22" width="16" height="36"/>
      <rect x="0.5" y="32" width="5.5" height="16"/><rect x="114" y="32" width="5.5" height="16"/></svg>
      <span class="pitch-dir">Attacking &rarr;</span>`;
  }

  // ---- matches: every match this season, the friendly he filmed marked
  function paintMatches() {
    $('pfMatches').innerHTML = [...P.matches].reverse().map(m => {
      const up = m.source === 'upload';
      const href = `${APP}/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}`;
      return `<li><a href="${esc(href)}" target="_blank" rel="noopener">
        <span class="pf-round">${esc(roundName(m))}</span>
        <span class="pf-vs">${esc(vsLine(m))}${up ? ' <span class="badge filmed">Filmed by Femi</span>' : ''}</span>
        <span class="pf-mm muted">${esc(m.home ? 'At home' : 'Away')}</span>
        <span class="pf-open">Open on Home &#8599;</span></a></li>`;
    }).join('');
  }

  // ---- your uploads: each upload, with every agent step it went through and how long each took
  const dur = (ms) => ms >= 60000 ? `${Math.floor(ms / 60000)} min ${Math.round(ms % 60000 / 1000)} s` : ms >= 1000 ? `${Math.round(ms / 1000)} s` : `${ms} ms`;
  function paintUploads() {
    if (!U.length) { $('pfUploads').innerHTML = '<p class="muted">No uploads yet. Add a match to see Regista\'s agents work on it here.</p>'; return; }
    $('pfUploads').innerHTML = U.map(u => {
      const total = u.stages.reduce((a, s) => a + (s.ms || 0), 0);
      const when = new Date(u.created_at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
      const status = u.status === 'done' ? 'Done' : u.status === 'needs_review' ? 'Waiting for you' : u.status === 'failed' ? 'Failed' : 'Working';
      const clips = (u.stages.find(s => s.role === 'clips') || {}).note || '';
      return `<article class="pf-up">
        <div class="pf-uphead"><div><h3>Friendly v ${esc(u.opponent?.name || '')} <span class="badge filmed">Filmed by Femi</span></h3>
          <p class="muted small">Uploaded ${esc(when)} · ${esc((u.size_bytes / 1048576).toFixed(1))} MB · processed in ${esc(dur(total))} on Azure Container Apps</p></div>
          <span class="pf-status ${u.status === 'done' ? 'ok' : ''}">${esc(status)}</span></div>
        <ol class="pf-steps">${u.stages.map(s => `<li class="${s.status === 'ok' ? 'ok' : 'bad'}"><span class="pf-tick" aria-hidden="true">${s.status === 'ok' ? '&#10003;' : '!'}</span>
          <span class="pf-sname">${esc(STAGES[s.role] || s.role)}</span><span class="pf-snote">${esc(s.note || '')}</span><span class="pf-sms">${esc(dur(s.ms || 0))}</span></li>`).join('')}</ol>
        ${u.match_id ? `<p class="pf-upres"><b>${esc(clips)}</b> · <a href="${esc(APP + (u.links?.clip_view || ''))}" target="_blank" rel="noopener">Open the match on Home &#8599;</a></p>` : ''}
      </article>`;
    }).join('');
  }

  // ---- clicks. The view opens at the top (the #profile link would otherwise scroll its section under the header).
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  const toTop = () => { if (location.hash === '#profile') for (const ms of [0, 60, 250]) setTimeout(() => window.scrollTo(0, 0), ms); };
  window.addEventListener('hashchange', toTop); window.addEventListener('load', toTop); toTop();
  $('profile').addEventListener('click', (e) => {
    const c = e.target.closest('[data-clip]'), s = e.target.closest('[data-stat]');
    if (c) { e.preventDefault(); reel = null; play(c.dataset.clip); return; }
    if (s) { e.preventDefault(); openStat(s.dataset.stat, s.classList.contains('pf-tile')); }
  });
  const addBox = $('pfAdd'), addBtn = $('pfAddBtn');
  const toggleAdd = (open) => { addBox.hidden = !open; addBtn.setAttribute('aria-expanded', String(open)); $('pfAddNote').textContent = ''; if (open) addBox.querySelector('input').focus(); };
  addBtn.onclick = () => toggleAdd(addBox.hidden);
  $('pfAddCancel').onclick = () => { toggleAdd(false); addBtn.focus(); };
  addBox.addEventListener('submit', (e) => {
    e.preventDefault();
    $('pfAddNote').textContent = 'Sandbox: nothing was uploaded. On the live app an upload goes to Azure Storage, a queue hands it to the vision job on Azure Container Apps, and its progress shows under Your uploads. Uploads need the admin key.';
  });
})();
