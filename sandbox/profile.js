// The Player dashboard: Femi Toure's six sections under Player profile (#profile/<section>). profile.json holds real data
// read from the live app on 2026-10-23: his profile (GET /api/players/pl_bro_09), his upload (/api/player/uploads), and
// his club (league squad, results, table from /api/season). Messages, settings and edits are mocks: nothing is sent or
// saved. Clips play from the live app.
(function () {
  const $ = (id) => document.getElementById(id);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
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
  const SECTIONS = ['overview', 'me', 'matches', 'messages', 'team', 'settings'];
  const short = (title) => String(title).replace(/^.*?: /, '');
  // Clip ids are numbered per match (Femi is t_away_09 in every away match), so a clip is known by match and clip id.
  const key = (m) => `${m.match_id}|${m.clip_id}`;

  let P = null, U = [], C = null, APP = '';
  const clipOf = new Map();
  const me = { name: '', position: '', kit: 0 };  // what Team > My details has saved (on this page only)

  // Messages: synthetic scouts at the league's synthetic clubs. Scouts start; Femi replies. clips: moment ids.
  const convos = [
    { id: 'c1', who: 'Maya Lindqvist', role: 'Chief scout', club: 'Fairhaven FC', verified: true, unread: 1, muted: false, blocked: false,
      msgs: [
        { from: 'them', when: 'Oct 21, 18:02', text: 'Hi Femi, we have been following your season. Six goals in eleven games stands out. Could you send a couple of your finishes?' },
        { from: 'me', when: 'Oct 21, 19:40', text: 'Thanks Maya. Here are two from this season.', clips: ['rl_r02_cal_bro|cl_t_away_09_000010', 'rl_r06_bro_eas|cl_t_home_09_000019'] },
        { from: 'them', when: 'Today, 09:15', text: 'The first one is exactly what we look for: early, low, across the keeper. Are you free for a call on Thursday?' },
      ] },
    { id: 'c2', who: 'Tomás Herrera', role: 'Scout', club: 'Ashby Athletic', verified: true, unread: 1, muted: false, blocked: false,
      msgs: [
        { from: 'them', when: 'Today, 08:30', text: 'Saw the nutmeg against us in round 10. Do you have footage from friendlies too? We would like to see more of you.' },
      ] },
    { id: 'c3', who: 'Priya Nair', role: 'Performance analyst', club: 'Dunmore City', verified: false, unread: 0, muted: false, blocked: false,
      msgs: [
        { from: 'them', when: 'Oct 18, 14:10', text: 'Your two goals against us in round 9 were well taken. Keep adding matches, it helps us see more of you.' },
        { from: 'me', when: 'Oct 18, 16:55', text: 'Will do, I have a friendly against Calder coming up.' },
      ] },
  ];
  let open = 'c1', draft = [];

  fetch('profile.json').then(r => r.json()).then(d => {
    P = d.profile; U = d.uploads || []; C = d.club; APP = d.app;
    for (const m of P.moments) clipOf.set(key(m), m);
    Object.assign(me, { name: P.name, position: P.position, kit: P.kit_number });
    paintAll();
    route();
  });

  // ------------------------------------------------------------------ routing: #profile/<section>[/add]
  function route() {
    const parts = location.hash.slice(1).split('/');
    const sub = $('pfSub');
    if (parts[0] !== 'profile') { sub.hidden = true; return; }
    const sec = SECTIONS.includes(parts[1]) ? parts[1] : 'overview';
    sub.hidden = false;
    for (const a of $$('a', sub)) { if (a.dataset.sub === sec) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }
    const cur = sub.querySelector('[aria-current]');  // on a phone the sections are a scrolling row: keep the current one in view
    if (cur && sub.scrollWidth > sub.clientWidth) sub.scrollLeft = cur.offsetLeft - sub.offsetLeft - 12;
    for (const v of $$('.pv')) v.hidden = v.dataset.sub !== sec;
    if (!P) return;
    if (sec !== 'me') $('pfVideo').pause();
    if (sec !== 'overview') $('ovVideo').pause();
    if (sec === 'matches' && parts[2] === 'add') toggleAdd(true);
    if (sec === 'messages') { convos.find(c => c.id === open).unread = 0; paintMessages(); }
    for (const ms of [0, 60, 250]) setTimeout(() => window.scrollTo(0, 0), ms);
  }
  if ('scrollRestoration' in history) history.scrollRestoration = 'manual';
  window.addEventListener('hashchange', route);
  route();

  function paintAll() {
    paintIdentity();
    paintSummary(); paintStrip(); play('pfVideo', key(best()[0]), false); paintNumbers(); paintPitch();
    paintMatches(); paintUploads(); paintQuestions();
    paintMessages();  // also paints the Overview, whose "Needs you" counts unread messages
    paintTeam();
  }

  // ------------------------------------------------------------------ shared pieces
  const roundName = (m) => m && m.round ? `Round ${m.round}` : 'Friendly';
  const matchOf = (id) => P.matches.find(m => m.match_id === id);
  const vsLine = (m) => {
    if (!m) return '';
    const us = P.club, them = m.opponent;
    if (!m.score) return `${m.home ? us : them} v ${m.home ? them : us}`;
    return m.home ? `${us} ${m.score} ${them}` : `${them} ${m.score} ${us}`;
  };
  const shirtSvg = (num) => `<svg viewBox="0 0 64 60" width="72" height="68"><path d="M20 4 L8 10 L2 24 L11 28 L14 22 L14 56 L50 56 L50 22 L53 28 L62 24 L56 10 L44 4 C42 9 37 12 32 12 C27 12 22 9 20 4 Z" fill="${esc(P.kit.primary)}" stroke="rgba(255,255,255,.25)" stroke-width="1"/>`
    + `<text x="32" y="44" text-anchor="middle" font-size="22" font-weight="800" fill="${esc(P.kit.secondary)}" font-family="-apple-system, Helvetica, Arial, sans-serif">${esc(num)}</text></svg>`;
  function paintIdentity() {
    for (const el of $$('.shirt')) el.innerHTML = shirtSvg(me.kit);
    for (const el of $$('.js-name')) el.textContent = me.name;
    for (const el of $$('.js-line')) el.textContent = `${POS[me.position] || me.position} · ${P.club} · Number ${me.kit}`;
    for (const el of $$('.js-apps')) el.textContent = `${P.appearances} matches · ${Math.round(P.minutes)} minutes`;
  }
  function best() {
    const seen = new Set();
    return [...P.moments].sort((a, b) => (b.watchability - a.watchability) || ((a.reason !== 'on_ball_main') - (b.reason !== 'on_ball_main')))
      .filter(m => !seen.has(key(m)) && seen.add(key(m))).slice(0, 8);
  }
  const reel = { on: false, ids: [], i: 0 };
  function play(videoId, clipId, start = true) {
    const m = clipOf.get(clipId);
    if (!m) return;
    const v = $(videoId), src = APP + m.video_url;
    if (v.getAttribute('src') !== src) { v.src = src; v.preload = start ? 'auto' : 'none'; }
    if (videoId === 'pfVideo') {
      $('pfNow').className = 'reason' + (m.reason === 'replay_appearance' ? ' replay' : '');
      $('pfNow').textContent = `${reel.on ? `Reel · clip ${reel.i} of ${reel.ids.length} · ` : ''}${REASONS[m.reason] || m.reason} · ${roundName(m)} · ${fmtTime(m.t)}`;
      $('pfTitle').textContent = short(m.title);
      $('pfTags').innerHTML = (m.tags || []).filter(t => !INTERNAL.test(t)).map(t => `<span>${esc(tagLabel(t))}</span>`).join('');
      for (const b of $$('.pf-clip')) b.classList.toggle('on', b.dataset.clip === clipId);
      if (start) v.closest('.pf-best').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
    if (start) v.play().catch(() => {});
  }

  // ------------------------------------------------------------------ Overview
  function paintOverview() {
    const unread = convos.reduce((a, c) => a + (c.blocked ? 0 : c.unread), 0);
    const up = U[0];
    const clips = up ? (up.stages.find(s => s.role === 'clips') || {}).note || '' : '';
    const needs = [];
    if (unread) needs.push(['messages', `${unread} new message${unread === 1 ? '' : 's'} from scouts`, convos.filter(c => c.unread && !c.blocked).map(c => `${c.who}, ${c.club}`).join(' · '), 'Read']);
    if (up) needs.push(['matches', up.status === 'done' ? `Your friendly v ${up.opponent?.name} is ready` : 'Your upload is being processed', clips || 'Regista\'s agents are working on it', 'See it']);
    needs.push(['matches', 'No "Is this you?" questions waiting', 'You answered the last two, both yes', 'Matches']);
    $('ovNeeds').innerHTML = needs.map(([sec, h, sub, cta], i) => `<a class="ov-need${i === 0 && unread ? ' hot' : ''}" href="#profile/${sec}">
      <span class="ov-nh">${esc(h)}</span><span class="ov-ns">${esc(sub)}</span><span class="ov-cta">${esc(cta)} &rarr;</span></a>`).join('');
    const tiles = [['Matches', P.appearances, `${Math.round(P.minutes)} minutes`], ...['goals', 'assists', 'shots'].map(k => [P.stat_labels[k], P.counts[k],
      P.percentiles[k] >= 100 ? 'Best of the league\'s forwards' : `Higher than ${P.percentiles[k]}% of forwards`])];
    $('ovSeason').innerHTML = tiles.map(([k, n, sub]) => `<div class="ov-tile"><span class="pf-n">${esc(n)}</span><span class="pf-k">${esc(k)}</span><span class="pf-rate">${esc(sub)}</span></div>`).join('');
    const top = best()[0];
    play('ovVideo', key(top), false);
    $('ovNow').textContent = `${REASONS[top.reason]} · ${roundName(top)} · ${vsLine(matchOf(top.match_id))}`;
    $('ovTitle').textContent = short(top.title);
    const when = up ? new Date(up.created_at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) : '';
    const last = [...C.results].sort((a, b) => b.round - a.round).slice(0, 2);
    const act = [
      ['msg', 'Today', 'Maya Lindqvist (Fairhaven FC) replied about your finishing', 'messages'],
      ['msg', 'Today', 'Tomás Herrera (Ashby Athletic) sent you a message', 'messages'],
      ...(up ? [['up', when, `Your friendly v ${up.opponent?.name} was processed: ${clips}`, 'matches']] : []),
      ...last.map(r => ['match', new Date(r.date).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }), `Round ${r.round}: ${r.home} ${r.score} ${r.away}`, 'me']),
    ];
    $('ovActivity').innerHTML = act.map(([k, w, t, sec]) => `<li><span class="ov-dot k-${k}" aria-hidden="true"></span><a href="#profile/${sec}">${esc(t)}</a><span class="muted small">${esc(w)}</span></li>`).join('');
  }

  // ------------------------------------------------------------------ My profile (what scouts see)
  function paintSummary() {
    const S = new Map((P.summary.sources || []).map(s => [s.id, s]));
    $('pfSummary').innerHTML = P.summary.sentences.map(x => {
      const src = (x.sources || []).map(id => S.get(id)).filter(Boolean)[0];
      if (!src) return `<span>${esc(x.text)}</span>`;
      const data = src.type === 'moment' ? `data-clip="${esc(key(src))}"` : `data-stat="${esc(src.key)}"`;
      return `<a href="#profile/me" class="cite" ${data}>${esc(x.text)}</a>`;
    }).join(' ');
    $('pfSumBy').textContent = String(P.summary.model || '').startsWith('foundry') ? 'Written by Microsoft Foundry from his numbers.'
      : 'Written by Regista from his numbers. Pick a sentence to see where it comes from.';
  }
  function paintStrip() {
    $('pfStrip').innerHTML = best().map(m => `<li><button type="button" class="pf-clip" data-clip="${esc(key(m))}">
      <span class="reason ${m.reason === 'replay_appearance' ? 'replay' : ''}">${esc(REASONS[m.reason] || m.reason)} · ${esc(roundName(m))}</span>
      <span class="pf-ctitle">${esc(short(m.title))}</span><span class="pf-cmatch">${esc(vsLine(matchOf(m.match_id)))}</span></button></li>`).join('');
  }
  $('pfReel').onclick = () => { Object.assign(reel, { on: true, ids: best().map(key), i: 1 }); play('pfVideo', reel.ids[0]); };
  $('pfVideo').addEventListener('ended', () => {
    if (!reel.on) return;
    if (reel.i >= reel.ids.length) { reel.on = false; return; }
    reel.i++; play('pfVideo', reel.ids[reel.i - 1]);
  });
  const pctText = (p) => p >= 100 ? 'Best of the league\'s forwards' : `Higher than ${p}% of the league's forwards`;
  function paintNumbers() {
    $('pfTiles').innerHTML = HEADLINE.map(k => `<button type="button" class="pf-tile" data-stat="${esc(k)}" aria-pressed="false">
      <span class="pf-n">${esc(P.counts[k])}</span><span class="pf-k">${esc(P.stat_labels[k] || k)}</span>
      <span class="pf-rate">${esc(P.per90[k].toFixed(2))} per 90 minutes</span>
      <span class="pf-pbar"><i style="width:${Math.max(3, P.percentiles[k])}%"></i></span><span class="pf-pct">${esc(pctText(P.percentiles[k]))}</span></button>`).join('');
    const r = P.ratios;
    $('pfRatios').innerHTML = [['passes completed', r.pass_accuracy], ['shots on target', r.shot_accuracy], ['take-ons won', r.take_on_success]]
      .map(([k, v]) => `<span><b>${esc(Math.round(v * 100))}%</b> ${esc(k)}</span>`).join('');
  }
  function openStat(key, toggle) {
    const box = $('pfEvidence');
    const closing = toggle && box.dataset.stat === key && !box.hidden;
    for (const t of $$('.pf-tile')) t.setAttribute('aria-pressed', String(t.dataset.stat === key && !closing));
    if (closing) { box.hidden = true; box.dataset.stat = ''; return; }
    const ev = P.evidence[key] || [];
    box.dataset.stat = key; box.hidden = false;
    box.innerHTML = `<h3>${esc(P.counts[key])} ${esc((P.stat_labels[key] || key).toLowerCase())}, verified by Regista</h3><ol>${ev.map(e => {
      const m = matchOf(e.match_id), c = e.clip_id && clipOf.get(key(e));
      const where = `${roundName(m)} · ${vsLine(m)} · ${fmtTime(e.t)}`;
      return c ? `<li><button type="button" class="link" data-clip="${esc(key(e))}">${esc(short(c.title))}</button> <span class="muted">${esc(where)}</span></li>`
        : `<li><span>${esc(where)}</span> <span class="muted">· in the match, no clip of its own</span></li>`;
    }).join('')}</ol>`;
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  function paintPitch() {
    const g = P.grid, max = Math.max(1, ...g.flat());
    const cells = g.map((row, y) => row.map((n, x) => `<i style="grid-row:${y + 1};grid-column:${x + 1};opacity:${n ? (0.12 + 0.88 * n / max).toFixed(2) : 0}" title="${n} touches"></i>`).join('')).join('');
    $('pfPitch').innerHTML = `<div class="heat">${cells}</div><svg viewBox="0 0 120 80" preserveAspectRatio="none" aria-hidden="true">
      <rect x="0.5" y="0.5" width="119" height="79"/><line x1="60" y1="0" x2="60" y2="80"/><circle cx="60" cy="40" r="9"/>
      <rect x="0.5" y="22" width="16" height="36"/><rect x="103.5" y="22" width="16" height="36"/>
      <rect x="0.5" y="32" width="5.5" height="16"/><rect x="114" y="32" width="5.5" height="16"/></svg><span class="pitch-dir">Attacking &rarr;</span>`;
  }

  // ------------------------------------------------------------------ Matches & videos
  function paintMatches() {
    const html = [...P.matches].reverse().map(m => {
      const href = `${APP}/?match=${encodeURIComponent(m.match_id)}&player=${encodeURIComponent(m.player_id)}`;
      return `<li><a href="${esc(href)}" target="_blank" rel="noopener"><span class="pf-round">${esc(roundName(m))}</span>
        <span class="pf-vs">${esc(vsLine(m))}${m.source === 'upload' ? ' <span class="badge filmed">Filmed by you</span>' : ''}</span>
        <span class="pf-mm muted">${esc(m.home ? 'At home' : 'Away')}</span><span class="pf-open">Open on Home &#8599;</span></a></li>`;
    }).join('');
    for (const el of $$('.js-matches')) el.innerHTML = html;
    $('pfOpp').innerHTML = [...new Set(P.matches.map(m => m.opponent))].sort().map(o => `<option>${esc(o)}</option>`).join('');
  }
  const dur = (ms) => ms >= 60000 ? `${Math.floor(ms / 60000)} min ${Math.round(ms % 60000 / 1000)} s` : ms >= 1000 ? `${Math.round(ms / 1000)} s` : `${ms} ms`;
  function paintUploads() {
    if (!U.length) { $('pfUploads').innerHTML = '<p class="muted">No uploads yet. Add a match to see Regista\'s agents work on it here.</p>'; return; }
    $('pfUploads').innerHTML = U.map(u => {
      const total = u.stages.reduce((a, s) => a + (s.ms || 0), 0);
      const when = new Date(u.created_at * 1000).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
      const status = u.status === 'done' ? 'Done' : u.status === 'needs_review' ? 'Waiting for you' : u.status === 'failed' ? 'Failed' : 'Working';
      const clips = (u.stages.find(s => s.role === 'clips') || {}).note || '';
      return `<article class="pf-up"><div class="pf-uphead"><div><h3>Friendly v ${esc(u.opponent?.name || '')}</h3>
          <p class="muted small">Uploaded ${esc(when)} · ${esc((u.size_bytes / 1048576).toFixed(1))} MB · processed in ${esc(dur(total))} on Azure Container Apps</p></div>
          <span class="pf-status ${u.status === 'done' ? 'ok' : ''}">${esc(status)}</span></div>
        <ol class="pf-steps">${u.stages.map(s => `<li class="${s.status === 'ok' ? 'ok' : 'bad'}"><span class="pf-tick" aria-hidden="true">${s.status === 'ok' ? '&#10003;' : '!'}</span>
          <span class="pf-sname">${esc(STAGES[s.role] || s.role)}</span><span class="pf-snote">${esc(s.note || '')}</span><span class="pf-sms">${esc(dur(s.ms || 0))}</span></li>`).join('')}</ol>
        ${u.match_id ? `<p class="pf-upres"><b>${esc(clips)}</b> · <a href="${esc(APP + (u.links?.clip_view || ''))}" target="_blank" rel="noopener">Open the match on Home &#8599;</a></p>` : ''}</article>`;
    }).join('');
  }
  function paintQuestions() {
    const answered = U.flatMap(u => (u.notes || []).filter(n => /answer/.test(n)).map(n => `Friendly v ${u.opponent?.name}: ${n.replace('answer(s)', 'answers')}`));
    $('pfQuestions').innerHTML = `<p class="pf-qnone"><span class="pf-tick" aria-hidden="true">&#10003;</span> No questions waiting.</p>`
      + (answered.length ? `<p class="muted small">${answered.map(esc).join('<br>')}</p>` : '');
  }
  const addBox = $('pfAdd'), addBtn = $('pfAddBtn');
  function toggleAdd(open) {
    addBox.hidden = !open; addBtn.setAttribute('aria-expanded', String(open)); $('pfAddNote').textContent = '';
    if (open) setTimeout(() => addBox.querySelector('input').focus(), 300);
  }
  addBtn.onclick = () => toggleAdd(addBox.hidden);
  $('pfAddCancel').onclick = () => { toggleAdd(false); addBtn.focus(); };
  addBox.addEventListener('submit', (e) => {
    e.preventDefault();
    $('pfAddNote').textContent = 'Sandbox: nothing was uploaded. On the live app an upload goes to Azure Storage, a queue hands it to the vision job on Azure Container Apps, and its progress shows under Your uploads. Uploads need the admin key.';
  });

  // ------------------------------------------------------------------ Messages
  function clipCard(id, removable = false) {
    const m = clipOf.get(id);
    if (!m) return '';
    return `<div class="mx-clip"><video controls playsinline preload="none" src="${esc(APP + m.video_url)}"></video>
      <div class="mx-cinfo"><span class="reason">${esc(REASONS[m.reason] || m.reason)} · ${esc(roundName(m))}</span><b>${esc(short(m.title))}</b>
      <span class="muted small">${esc(vsLine(matchOf(m.match_id)))}</span></div>${removable ? `<button type="button" class="link mx-unpick" data-unpick="${esc(id)}" aria-label="Remove ${esc(short(m.title))}">&times;</button>` : ''}</div>`;
  }
  function paintDraft() { $('mxDraft').innerHTML = draft.map(id => clipCard(id, true)).join(''); $('mxDraft').hidden = !draft.length; }
  function paintMessages() {
    const unread = convos.reduce((a, c) => a + (c.blocked ? 0 : c.unread), 0);
    $('pfUnread').textContent = unread ? String(unread) : '';
    $('mxList').innerHTML = convos.map(c => {
      const last = c.msgs[c.msgs.length - 1];
      return `<li><button type="button" class="mx-item${c.id === open ? ' on' : ''}${c.blocked ? ' blocked' : ''}" data-convo="${c.id}">
        <span class="mx-av" aria-hidden="true">${esc(c.who.split(' ').map(w => w[0]).join(''))}</span>
        <span class="mx-who"><b>${esc(c.who)}${c.verified ? ' <span class="mx-ver" title="Verified scout">&#10003;</span>' : ''}</b><span class="muted small">${esc(c.role)}, ${esc(c.club)}</span>
          <span class="mx-last">${esc(c.blocked ? 'Blocked' : (last.from === 'me' ? 'You: ' : '') + (last.text || 'Sent a moment'))}</span></span>
        <span class="mx-meta"><span class="muted small">${esc(last.when.split(',')[0])}</span>${c.unread && !c.blocked ? `<span class="count">${c.unread}</span>` : ''}${c.muted ? '<span class="muted small">Muted</span>' : ''}</span></button></li>`;
    }).join('');
    const c = convos.find(x => x.id === open);
    $('mxHead').innerHTML = `<div><b>${esc(c.who)}</b>${c.verified ? ' <span class="mx-ver">&#10003; Verified scout</span>' : ''}
      <p class="muted small">${esc(c.role)}, ${esc(c.club)}</p></div>
      <div class="mx-acts"><button type="button" class="alt" data-act="mute">${c.muted ? 'Unmute' : 'Mute'}</button><button type="button" class="alt" data-act="block">${c.blocked ? 'Unblock' : 'Block'}</button></div>`;
    $('mxMsgs').innerHTML = c.msgs.map(m => `<li class="mx-msg ${m.from}"><div class="mx-bubble">${m.text ? `<p>${esc(m.text)}</p>` : ''}${(m.clips || []).map(id => clipCard(id)).join('')}</div>
      <span class="muted small">${esc(m.from === 'me' ? 'You' : c.who.split(' ')[0])} · ${esc(m.when)}</span></li>`).join('')
      + (c.blocked ? '<li class="mx-blocked muted small">You blocked this scout. They cannot message you.</li>' : '');
    paintDraft();
    $('mxCompose').hidden = c.blocked;
    $('mxPickList').innerHTML = best().map(m => `<li><label><input type="checkbox" value="${esc(key(m))}"${draft.includes(key(m)) ? ' checked' : ''}>
      <span><b>${esc(short(m.title))}</b> <span class="muted small">${esc(roundName(m))} · ${esc(vsLine(matchOf(m.match_id)))}</span></span></label></li>`).join('');
    const box = $('mxMsgs'); box.scrollTop = box.scrollHeight;
    paintOverview();
  }
  $('mxList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-convo]'); if (!b) return;
    open = b.dataset.convo; convos.find(c => c.id === open).unread = 0; draft = [];
    document.querySelector('.mx').classList.add('reading');  // on a phone: the thread replaces the list
    paintMessages();
  });
  $('mxBack').onclick = () => document.querySelector('.mx').classList.remove('reading');
  $('mxHead').addEventListener('click', (e) => {
    const b = e.target.closest('[data-act]'); if (!b) return;
    const c = convos.find(x => x.id === open);
    if (b.dataset.act === 'mute') c.muted = !c.muted; else c.blocked = !c.blocked;
    paintMessages();
  });
  $('mxAttach').onclick = () => { const p = $('mxPicker'); p.hidden = !p.hidden; $('mxAttach').setAttribute('aria-expanded', String(!p.hidden)); };
  $('mxPickList').addEventListener('change', (e) => {
    const v = e.target.value; draft = e.target.checked ? [...draft, v] : draft.filter(x => x !== v);
    paintDraft();
  });
  $('mxDraft').addEventListener('click', (e) => {
    const b = e.target.closest('[data-unpick]'); if (!b) return;
    draft = draft.filter(x => x !== b.dataset.unpick); paintMessages();
  });
  $('mxCompose').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $('mxText').value.trim();
    if (!text && !draft.length) return;
    convos.find(c => c.id === open).msgs.push({ from: 'me', when: 'Just now', text, clips: draft });
    draft = []; $('mxText').value = ''; $('mxPicker').hidden = true; $('mxAttach').setAttribute('aria-expanded', 'false');
    paintMessages();
    $('mxText').focus();
  });

  // ------------------------------------------------------------------ Team: my details + my club
  const ordinal = (n) => `${n}${['th', 'st', 'nd', 'rd'][(n % 100 > 10 && n % 100 < 14) ? 0 : n % 10 < 4 ? n % 10 : 0]}`;
  function paintTeam() {
    $('tmName').value = me.name; $('tmPos').value = me.position; $('tmKit').value = me.kit;
    $('tmCrest').style.background = `linear-gradient(135deg, ${C.kit.primary} 50%, ${C.kit.secondary} 50%)`;
    $('tmClubHead').textContent = C.name;
    const row = C.table.find(t => t.club_id === C.club_id);
    $('tmClubLine').textContent = `${C.league} ${C.season} · ${C.ground} · ${ordinal(row.position)} in the table, ${row.points} points`;
    const squad = [...C.squad].sort((a, b) => a.kit_number - b.kit_number);
    $('tmSquad').innerHTML = squad.map(p => {
      const you = p.global_id === P.global_id;
      return `<li class="${you ? 'you' : ''}"><span class="tm-num">${esc(you ? me.kit : p.kit_number)}</span>
      <span>${esc(you ? me.name : p.name)}${you ? ' <span class="badge filmed">You</span>' : ''}</span>
      <span class="muted small">${esc(POS[you ? me.position : p.position] || p.position)}${p.starter ? '' : ' · sub'}</span></li>`;
    }).join('');
    $('tmResults').innerHTML = [...C.results].sort((a, b) => b.round - a.round).map(r => {
      const res = r.us_goals > r.them_goals ? 'W' : r.us_goals < r.them_goals ? 'L' : 'D';
      return `<li><span class="tm-res r-${res}" title="${{ W: 'Won', L: 'Lost', D: 'Drawn' }[res]}">${res}</span><span class="pf-round">Round ${r.round}</span><span>${esc(r.home)} ${esc(r.score)} ${esc(r.away)}</span></li>`;
    }).join('');
    $('tmTable').innerHTML = `<thead><tr><th>#</th><th>Club</th><th title="Played">P</th><th title="Won">W</th><th title="Drawn">D</th><th title="Lost">L</th><th title="Goal difference">GD</th><th title="Points">Pts</th></tr></thead><tbody>`
      + C.table.map(t => `<tr class="${t.club_id === C.club_id ? 'you' : ''}"><td>${t.position}</td><td>${esc(t.club)}</td><td>${t.played}</td><td>${t.won}</td><td>${t.drawn}</td><td>${t.lost}</td><td>${t.goal_difference > 0 ? '+' : ''}${t.goal_difference}</td><td><b>${t.points}</b></td></tr>`).join('')
      + '</tbody>';
  }
  $('tmForm').addEventListener('submit', (e) => {
    e.preventDefault();
    me.name = $('tmName').value.trim() || P.name; me.position = $('tmPos').value; me.kit = Number($('tmKit').value) || P.kit_number;
    paintIdentity(); paintTeam();
    $('tmNote').textContent = 'Saved. Sandbox: only this page changed; on the live app your profile would update for scouts too.';
  });

  // ------------------------------------------------------------------ Settings
  $('stOut').onclick = () => { $('stNote').textContent = 'Sandbox: there is no sign-in yet, so there is nothing to sign out of.'; };

  // ------------------------------------------------------------------ clicks inside My profile
  $('pv-me').addEventListener('click', (e) => {
    const c = e.target.closest('[data-clip]'), s = e.target.closest('[data-stat]');
    if (c) { e.preventDefault(); reel.on = false; play('pfVideo', c.dataset.clip); return; }
    if (s) { e.preventDefault(); openStat(s.dataset.stat, s.classList.contains('pf-tile')); }
  });
})();
