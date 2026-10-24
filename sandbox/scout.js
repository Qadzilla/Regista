// The Scout dashboard: Maya Lindqvist, chief scout at Fairhaven FC (synthetic, like the league). Eight sections under
// Scout (#scout/<section>), and #scout/player/<id> for one player: the same profile page the player sees as "My
// profile" (profile-view.js), with the scout bar on top. scout.json holds real data read from the live app on
// 2026-10-23: every league player's card, full profiles for her shortlist, four Scout agent answers (rules engine),
// Fairhaven's squad and the table. Messages, notes, stages, reports and needs are mocks: nothing is sent or saved.
(function () {
  const $ = (id) => document.getElementById(id);
  const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
  const F = () => window.PF;
  const esc = (v) => String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const POS = { FW: 'Forward', MF: 'Midfielder', DF: 'Defender', GK: 'Goalkeeper' };
  const GROUP = { FW: 'forwards', MF: 'midfielders', DF: 'defenders', GK: 'goalkeepers' };
  const LEAD = { FW: ['goals', 'shots', 'assists'], MF: ['recoveries', 'tackles_won', 'key_passes'], DF: ['interceptions', 'tackles_won', 'recoveries'], GK: ['saves', 'passes_completed', 'recoveries'] };
  const STAGES = ['Watching', 'Contacted', 'Trial', 'Offer'];
  const SECTIONS = ['overview', 'find', 'terminal', 'player', 'shortlist', 'reports', 'messages', 'team', 'settings'];

  let D = null, APP = '', byId = new Map(), playerView = null, current = null;
  const clipOf = new Map();  // match|clip -> moment, across every saved profile

  // Her shortlist: a stage and a note per player (mock).
  const shortlist = new Map([
    ['pl_bro_09', { stage: 'Contacted', note: 'Top scorer in the league. Finishes early and low across the keeper. Call booked for Thursday.' }],
    ['pl_ash_10', { stage: 'Watching', note: 'Beats players in tight spaces. Check his decisions in the final third.' }],
    ['pl_ash_09', { stage: 'Watching', note: 'Third for goals per 90. Watch more of his movement off the ball.' }],
    ['pl_dun_06', { stage: 'Trial', note: 'Wins the ball back. Trial week booked for 9 November.' }],
    ['pl_eas_03', { stage: 'Offer', note: 'Reads the game: most interceptions among defenders. Offer sent, waiting for his answer.' }],
  ]);
  const compareSel = new Set();
  // Fairhaven's needs (editable): each lists the players who fit, from the real numbers.
  const needs = [
    { title: 'A forward who scores', pos: 'FW', stat: 'goals', pct: 75 },
    { title: 'A midfielder who wins the ball back', pos: 'MF', stat: 'recoveries', pct: 75 },
    { title: 'A defender who reads the game', pos: 'DF', stat: 'interceptions', pct: 75 },
  ];
  // Reports: sections of text, each citing moments (match|clip keys) that play when clicked.
  const reports = [];
  let openReport = 0;
  // Messages: Maya's side. Scouts start conversations; the thread with Femi mirrors the one on his dashboard.
  const convos = [
    { id: 's1', gid: 'pl_eas_03', unread: 1, msgs: [
      { from: 'me', when: 'Oct 20, 11:00', text: 'Gino, Fairhaven would like to make you an offer for next season. The details are attached in our club portal.' },
      { from: 'them', when: 'Today, 10:05', text: 'Thank you, that means a lot. I am talking it through with my family. Could we speak early next week?' } ] },
    { id: 's2', gid: 'pl_bro_09', unread: 0, msgs: [
      { from: 'me', when: 'Oct 21, 18:02', text: 'Hi Femi, we have been following your season. Six goals in eleven games stands out. Could you send a couple of your finishes?' },
      { from: 'them', when: 'Oct 21, 19:40', text: 'Thanks Maya. Here are two from this season.', clips: ['rl_r02_cal_bro|cl_t_away_09_000010', 'rl_r06_bro_eas|cl_t_home_09_000019'] },
      { from: 'me', when: 'Today, 09:15', text: 'The first one is exactly what we look for: early, low, across the keeper. Are you free for a call on Thursday?' } ] },
    { id: 's3', gid: 'pl_dun_06', unread: 0, msgs: [
      { from: 'me', when: 'Oct 16, 15:20', text: 'Farid, your trial is booked for the week of 9 November. Bring boots for grass and artificial turf.' },
      { from: 'them', when: 'Oct 16, 17:02', text: 'Great, see you then.' } ] },
  ];
  let openConvo = 's1';

  fetch('scout.json').then(r => r.json()).then(d => {
    D = d; APP = d.app;
    for (const p of d.players) byId.set(p.global_id, p);
    for (const P of Object.values(d.profiles)) for (const m of P.moments) clipOf.set(F().key(m), m);
    seedReport();
    paintFind(); paintTeam(); paintMessages(); paintBoard(); paintReports();
    route();
  });

  // ------------------------------------------------------------------ routing: #scout/<section>[/<id>]
  function route() {
    const parts = location.hash.slice(1).split('/');
    const sub = $('scSub');
    if (parts[0] !== 'scout') { sub.hidden = true; if (playerView) playerView.pause(); return; }
    const sec = SECTIONS.includes(parts[1]) ? parts[1] : 'overview';
    sub.hidden = false;
    const navSec = sec === 'player' ? 'find' : sec;
    for (const a of $$('a', sub)) { if (a.dataset.sub === navSec) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); }
    const cur = sub.querySelector('[aria-current]');
    if (cur && sub.scrollWidth > sub.clientWidth) sub.scrollLeft = cur.offsetLeft - sub.offsetLeft - 12;
    for (const v of $$('[data-sc]')) v.hidden = v.dataset.sc !== sec;
    if (!D) return;
    if (sec !== 'player' && playerView) playerView.pause();
    for (const v of $$('#scout video')) if (!v.closest('[data-sc="player"]') || sec !== 'player') v.pause();
    if (sec === 'overview') paintOverview();
    if (sec === 'player') openPlayer(parts[2]);
    if (sec === 'messages') { const c = convos.find(x => x.id === openConvo); if (c) c.unread = 0; paintMessages(); }
    for (const ms of [0, 60, 250]) setTimeout(() => window.scrollTo(0, 0), ms);
  }
  window.addEventListener('hashchange', route);
  route();

  // ------------------------------------------------------------------ shared pieces
  const headOf = (p, k) => p.headline?.[k] || { count: 0, per90: 0, percentile: 0, label: k };
  const fits = (n) => D.players.filter(p => p.position === n.pos && p.club_id !== D.club.club_id && headOf(p, n.stat).percentile >= n.pct)
    .sort((a, b) => headOf(b, n.stat).per90 - headOf(a, n.stat).per90);
  // The stat a player is best at among the ones their position is judged on (what a shortlist card leads with).
  const strongest = (p) => (LEAD[p.position] || LEAD.FW).reduce((a, k) => headOf(p, k).percentile > headOf(p, a).percentile ? k : a);
  const label = (k) => (D.stats.find(s => s.key === k) || {}).label || k.replace(/_/g, ' ');
  const shirt = (p) => F().shirtSvg(p.kit, p.kit_number).replace('width="72" height="68"', 'width="40" height="38"');
  function card(p) {
    const sl = shortlist.get(p.global_id);
    return `<a class="sc-card" href="#scout/player/${esc(p.global_id)}">
      <span class="sc-chead"><span class="sc-shirt" aria-hidden="true">${shirt(p)}</span><span><b>${esc(p.name)}</b>
        <span class="muted small">${esc(POS[p.position])} · ${esc(p.club)}</span></span>${sl ? `<span class="sc-stage s-${esc(sl.stage)}">${esc(sl.stage)}</span>` : ''}</span>
      <span class="sc-cstats">${(LEAD[p.position] || LEAD.FW).map(k => { const h = headOf(p, k); return `<span><b>${esc(h.per90.toFixed(2))}</b> ${esc(label(k).toLowerCase())} per 90<i style="width:${Math.max(3, h.percentile)}%"></i></span>`; }).join('')}</span>
      <span class="muted small">${esc(p.appearances)} matches · ${esc(Math.round(p.minutes))} minutes</span></a>`;
  }

  // ------------------------------------------------------------------ Overview
  function paintOverview() {
    const unread = convos.reduce((a, c) => a + c.unread, 0);
    const uploads = [...shortlist.keys()].flatMap(gid => (D.profiles[gid]?.matches || []).filter(m => m.source === 'upload').map(m => [gid, m]));
    const fitCount = new Set(needs.flatMap(n => fits(n).map(p => p.global_id))).size;
    const needsHtml = [];
    if (unread) {
      const c = convos.find(x => x.unread);
      needsHtml.push([`#scout/messages`, `${byId.get(c.gid).name} replied`, c.msgs[c.msgs.length - 1].text, 'Read', true]);
    }
    for (const [gid, m] of uploads) needsHtml.push([`#scout/player/${gid}`, `${byId.get(gid).name} added a match`, `A friendly v ${m.opponent}, filmed by the player and cut by Regista`, 'Watch']);
    needsHtml.push(['#scout/team', `${fitCount} players fit what Fairhaven needs`, needs.map(n => n.title.replace(/^A /, '')).join(' · '), 'See them']);
    $('scNeeds').innerHTML = needsHtml.map(([href, h, sub, cta, hot]) => `<a class="ov-need${hot ? ' hot' : ''}" href="${esc(href)}">
      <span class="ov-nh">${esc(h)}</span><span class="ov-ns">${esc(sub)}</span><span class="ov-cta">${esc(cta)} &rarr;</span></a>`).join('');
    $('scStageSum').innerHTML = STAGES.map(st => {
      const ps = [...shortlist].filter(([, v]) => v.stage === st).map(([gid]) => byId.get(gid));
      return `<a class="ov-tile sc-st" href="#scout/shortlist"><span class="sc-stage s-${esc(st)}">${esc(st)}</span><span class="pf-n">${ps.length}</span>
        <span class="pf-rate">${esc(ps.map(p => p.name).join(', ') || 'Nobody yet')}</span></a>`;
    }).join('');
    const act = [
      ['msg', 'Today', 'Gino Mensah replied about your offer', '#scout/messages'],
      ['msg', 'Today', 'You asked Femi Toure for a call on Thursday', '#scout/messages'],
      ['up', 'Oct 22', 'Femi Toure added a friendly v Calder Town', '#scout/player/pl_bro_09'],
      ['match', 'Oct 22', 'You wrote a report on Femi Toure: Sign', '#scout/reports'],
      ['match', 'Oct 16', 'Farid Vargas moved to Trial', '#scout/shortlist'],
    ];
    $('scActivity').innerHTML = act.map(([k, w, t, href]) => `<li><span class="ov-dot k-${k}" aria-hidden="true"></span><a href="${esc(href)}">${esc(t)}</a><span class="muted small">${esc(w)}</span></li>`).join('');
  }

  // ------------------------------------------------------------------ Find players: the Scout agent, filters, cards
  const ASKS = Object.keys({ 'Forwards who score the most': 0, 'Midfielders who win the ball back': 0, 'Who wins the most take-ons?': 0, 'Defenders with the most interceptions': 0 });
  const KEYS = [[/score|goal|finish|striker/, 0], [/ball back|recover|tackl|win.*ball|defensive mid/, 1], [/take.?on|dribbl|beat/, 2], [/intercept|defender|centre.?back|read/, 3]];
  function paintFind() {
    $('scExamples').innerHTML = ASKS.map(q => `<button type="button" class="chip" data-ask="${esc(q)}">${esc(q)}</button>`).join('');
    const keys = ['minutes', ...new Set(Object.values(LEAD).flat()), 'assists', 'take_ons_won', 'key_passes', 'saves'];
    $('scSort').innerHTML = [...new Set(keys)].map(k => `<option value="${esc(k)}">${esc(k === 'minutes' ? 'Minutes played' : label(k) + ' per 90')}</option>`).join('');
    paintCards();
  }
  function paintCards() {
    const q = $('scName').value.trim().toLowerCase(), pos = $('scPos').value, sort = $('scSort').value;
    const rows = D.players.filter(p => (!pos || p.position === pos) && (!q || `${p.name} ${p.club}`.toLowerCase().includes(q)))
      .sort((a, b) => sort === 'minutes' ? b.minutes - a.minutes : headOf(b, sort).per90 - headOf(a, sort).per90);
    $('scCount').textContent = `${rows.length} players · the Regista League ${D.season}`;
    $('scCards').innerHTML = rows.map(card).join('');
  }
  for (const id of ['scName', 'scPos', 'scSort']) $(id).addEventListener('input', paintCards);
  function ask(text) {
    const t = text.toLowerCase();
    const exact = ASKS.find(q => q.toLowerCase() === t);
    const hit = exact || ASKS[(KEYS.find(([re]) => re.test(t)) || [])[1]];
    const box = $('scAnswer'); box.hidden = false;
    $('scQ').value = text;
    if (!hit) {
      box.innerHTML = `<p class="muted">In the sandbox the Scout agent answers four questions, saved from the live app: ${ASKS.map(esc).join(' · ')}. Try one of them.</p>`;
      return;
    }
    const a = D.answers[hit];
    box.innerHTML = `<p class="sc-reply">${esc(a.reply)}</p>
      <div class="sc-mini">${a.players.map(p => `<a href="#scout/player/${esc(p.global_id)}" class="sc-minirow"><span class="sc-shirt" aria-hidden="true">${shirt(p)}</span>
        <span><b>${esc(p.name)}</b> <span class="muted small">${esc(POS[p.position])} · ${esc(p.club)}</span></span></a>`).join('')}</div>
      <details class="how"><summary>How the Scout agent answered · Data Search, no AI model · ${a.trace.length} steps</summary>
        <p class="small">Understood: ${esc(a.understood)}</p>
        <div class="times">${a.trace.map(s => `${esc(s.kind)} · ${esc(s.name)} · ${esc(s.ms < 1 ? '<1' : Math.round(s.ms))} ms`).join('<br>')}</div></details>`;
  }
  $('scAsk').addEventListener('submit', (e) => { e.preventDefault(); const t = $('scQ').value.trim(); if (t) ask(t); });
  $('scExamples').addEventListener('click', (e) => { const b = e.target.closest('[data-ask]'); if (b) ask(b.dataset.ask); });

  // ------------------------------------------------------------------ one player: the profile, with the scout bar
  function openPlayer(gid) {
    const p = byId.get(gid);
    if (!p) { location.hash = 'scout/find'; return; }
    current = gid;
    paintBar();
    $('scNoteBox').hidden = true;
    const P = D.profiles[gid];
    if (P) playerView = F().render($('scPlayerBody'), P, { app: APP });
    else {
      playerView = null;
      const keys = Object.keys(p.headline);
      $('scPlayerBody').innerHTML = `<header class="pf-head panel"><div class="shirt" aria-hidden="true">${F().shirtSvg(p.kit, p.kit_number)}</div>
        <div class="pf-who"><h1>${esc(p.name)}</h1><p class="pf-line">${esc(POS[p.position])} · ${esc(p.club)} · Number ${esc(p.kit_number)}</p>
        <p class="pf-line muted">${esc(p.appearances)} matches · ${esc(Math.round(p.minutes))} minutes</p></div></header>
        <section class="panel"><h2>Numbers</h2><p class="muted small">This season, against the league's other ${esc(GROUP[p.position])}.</p>
        <div class="pf-tiles">${keys.map(k => { const h = p.headline[k]; return `<div class="pf-tile"><span class="pf-n">${esc(h.count)}</span><span class="pf-k">${esc(h.label)}</span>
          <span class="pf-rate">${esc(h.per90.toFixed(2))} per 90 minutes</span><span class="pf-pbar"><i style="width:${Math.max(3, h.percentile)}%"></i></span>
          <span class="pf-pct">${esc(F().pctText(h.percentile, p.position))}</span></div>`; }).join('')}</div></section>
        <p class="pf-scouts">The sandbox holds full profiles (moments, summary, touch map, matches) for your shortlist only.
          <a href="${esc(`${APP}/players/${encodeURIComponent(gid)}`)}" target="_blank" rel="noopener">Open ${esc(p.name)}'s full profile on the live app &#8599;</a></p>`;
    }
  }
  function paintBar() {
    const p = byId.get(current), sl = shortlist.get(current);
    $('scBar').innerHTML = `<div class="sc-barwho"><b>${esc(p.name)}</b><span class="muted small">${esc(POS[p.position])} · ${esc(p.club)}</span></div>
      <label class="sc-stagepick"><span class="sr">Shortlist stage</span><select id="scStagePick">
        <option value="">Not on your shortlist</option>${STAGES.map(st => `<option${sl?.stage === st ? ' selected' : ''}>${st}</option>`).join('')}</select></label>
      <button type="button" class="alt" data-bar="message">Message</button>
      <button type="button" class="alt" data-bar="compare" aria-pressed="${compareSel.has(current)}">${compareSel.has(current) ? 'In compare' : 'Compare'}</button>
      <button type="button" class="alt" data-bar="notes" aria-expanded="${!$('scNoteBox').hidden}">Notes${sl?.note ? ' ·' : ''}</button>
      ${D.profiles[current] ? '<button type="button" data-bar="report">Write a report</button>' : ''}`;
    $('scStagePick').onchange = (e) => {
      const v = e.target.value;
      if (!v) { shortlist.delete(current); compareSel.delete(current); } else shortlist.set(current, { ...(shortlist.get(current) || { note: '' }), stage: v });
      paintBoard(); paintBar();
    };
  }
  $('scBar').addEventListener('click', (e) => {
    const b = e.target.closest('[data-bar]'); if (!b) return;
    const act = b.dataset.bar;
    if (act === 'message') return startConvo(current);
    if (act === 'compare') { compareSel.has(current) ? compareSel.delete(current) : compareSel.size < 3 && compareSel.add(current); paintBar(); paintBoard(); return; }
    if (act === 'notes') { const box = $('scNoteBox'); box.hidden = !box.hidden; $('scNote').value = shortlist.get(current)?.note || ''; paintBar(); if (!box.hidden) $('scNote').focus(); return; }
    if (act === 'report') { newReport(current); location.hash = 'scout/reports'; }
  });
  $('scNoteSave').onclick = () => {
    const note = $('scNote').value.trim();
    shortlist.set(current, { stage: shortlist.get(current)?.stage || 'Watching', note });
    $('scNoteBox').hidden = true; paintBar(); paintBoard();
  };
  $('scBack').onclick = () => { if (history.length > 1) history.back(); else location.hash = 'scout/find'; };

  // ------------------------------------------------------------------ Shortlist: stages and compare
  function paintBoard() {
    if (!D) return;
    $('scBoard').innerHTML = STAGES.map(st => {
      const ps = [...shortlist].filter(([, v]) => v.stage === st);
      return `<section class="sc-col panel"><h2><span class="sc-stage s-${esc(st)}">${esc(st)}</span> <span class="muted small">${ps.length}</span></h2>
        ${ps.map(([gid, v]) => { const p = byId.get(gid), k = strongest(p), h = headOf(p, k);
          return `<article class="sc-item"><a href="#scout/player/${esc(gid)}"><b>${esc(p.name)}</b></a>
            <span class="muted small">${esc(POS[p.position])} · ${esc(p.club)}</span>
            <span class="small">${esc(h.per90.toFixed(2))} ${esc(label(k).toLowerCase())} per 90 · ${esc(F().pctText(h.percentile, p.position).replace("the league's ", ''))}</span>
            ${v.note ? `<p class="sc-inote">${esc(v.note)}</p>` : ''}
            <div class="sc-iacts"><label class="sc-cmp"><input type="checkbox" data-cmp="${esc(gid)}"${compareSel.has(gid) ? ' checked' : ''}${!compareSel.has(gid) && compareSel.size >= 3 ? ' disabled' : ''}> Compare</label>
              <label><span class="sr">Move ${esc(p.name)} to</span><select data-move="${esc(gid)}">${STAGES.map(s2 => `<option${s2 === st ? ' selected' : ''}>${s2}</option>`).join('')}<option value="">Remove</option></select></label></div></article>`;
        }).join('') || '<p class="muted small">Nobody here yet.</p>'}</section>`;
    }).join('');
    $('scCompareGo').disabled = compareSel.size < 2;
    $('scCompareGo').textContent = compareSel.size ? `Compare (${compareSel.size})` : 'Compare';
  }
  $('scBoard').addEventListener('change', (e) => {
    const t = e.target;
    if (t.dataset.cmp) { t.checked ? compareSel.add(t.dataset.cmp) : compareSel.delete(t.dataset.cmp); paintBoard(); }
    if (t.dataset.move !== undefined) {
      if (!t.value) { shortlist.delete(t.dataset.move); compareSel.delete(t.dataset.move); } else shortlist.get(t.dataset.move).stage = t.value;
      paintBoard();
    }
  });
  $('scCompareGo').onclick = () => { paintCompare(); $('scCompare').scrollIntoView({ behavior: 'smooth', block: 'start' }); };
  function paintCompare() {
    const ps = [...compareSel].map(g => byId.get(g));
    const stats = [...new Set(ps.flatMap(p => LEAD[p.position] || LEAD.FW).concat(['goals', 'assists', 'key_passes', 'take_ons_won', 'tackles_won', 'interceptions', 'recoveries']))];
    const box = $('scCompare'); box.hidden = false;
    box.innerHTML = `<div class="pf-bar"><h2>Compare</h2><button type="button" class="alt" id="scCompareClose">Close</button></div>
      <p class="muted small">Per 90 minutes this season. Pick a number to see the moments behind it.</p>
      <div class="tablewrap"><table class="sc-ctable"><thead><tr><th></th>${ps.map(p => `<th><a href="#scout/player/${esc(p.global_id)}">${esc(p.name)}</a><span class="muted small">${esc(POS[p.position])} · ${esc(p.short_name)}</span></th>`).join('')}</tr></thead><tbody>
      ${stats.map(k => { const vals = ps.map(p => headOf(p, k).per90), top = Math.max(...vals);
        return `<tr><th>${esc(label(k))}</th>${ps.map((p, i) => `<td class="${vals[i] === top && top > 0 ? 'best' : ''}"><button type="button" class="link" data-ev="${esc(p.global_id)}|${esc(k)}">${esc(vals[i].toFixed(2))}</button></td>`).join('')}</tr>`; }).join('')}
      </tbody></table></div>
      <div class="sc-cev" id="scCev" hidden></div>`;
    $('scCompareClose').onclick = () => { box.hidden = true; };
  }
  $('scCompare').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ev]'), c = e.target.closest('[data-cplay]');
    if (c) { const m = clipOf.get(c.dataset.cplay), v = $('scCevVideo'); if (m && v) { v.src = APP + m.video_url; v.play().catch(() => {}); $('scCevNow').textContent = F().short(m.title); } return; }
    if (!b) return;
    const [gid, k] = b.dataset.ev.split('|'), P = D.profiles[gid], p = byId.get(gid), box = $('scCev');
    box.hidden = false;
    if (!P) { box.innerHTML = `<p class="muted small">The sandbox holds moments for your shortlist only.</p>`; return; }
    const ev = P.evidence?.[k] || [], vs = F().vsLineFor(P), matchOf = (id) => P.matches.find(m => m.match_id === id);
    box.innerHTML = `<h3>${esc(p.name)}: ${esc(P.counts[k])} ${esc(label(k).toLowerCase())}</h3>
      <div class="sc-cevgrid"><ol>${ev.map(e2 => { const m = matchOf(e2.match_id), c2 = e2.clip_id && clipOf.get(F().key(e2));
        return c2 ? `<li><button type="button" class="link" data-cplay="${esc(F().key(e2))}">${esc(F().short(c2.title))}</button> <span class="muted small">${esc(F().roundName(m))} · ${esc(vs(m))}</span></li>`
          : `<li><span class="small">${esc(F().roundName(m))} · ${esc(vs(m))} · ${esc(F().fmtTime(e2.t))}</span> <span class="muted small">no clip of its own</span></li>`; }).join('') || '<li class="muted small">None this season.</li>'}</ol>
      <div><div class="pf-screen"><video id="scCevVideo" controls playsinline preload="none"></video></div><p class="small" id="scCevNow"></p></div></div>`;
  });

  // ------------------------------------------------------------------ Reports
  function seedReport() {
    reports.push({ gid: 'pl_bro_09', date: 'Oct 22', verdict: 'Sign', title: 'Femi Toure, forward, Brookfield Rovers', sections: [
      { name: 'Summary', text: 'The league\'s top scorer: 6 goals in 11 matches, 1.78 per 90, the best of its 18 forwards. Finishes early and low, and is a threat from the first minute.', cites: ['rl_r02_cal_bro|cl_t_away_09_000010', 'rl_r09_bro_dun|cl_t_home_09_000007'] },
      { name: 'Strengths', text: 'Shoots often and on target (5.92 shots per 90, 70% on target). Links play too: 2.07 key passes per 90, higher than 88% of forwards.', cites: ['rl_r02_cal_bro|cl_t_away_09_000016', 'rl_r06_bro_eas|cl_t_home_09_000019'] },
      { name: 'Concerns', text: 'Wins half of his take-ons (50%). We would want more from him one against one; watch him against a deep block.', cites: ['rl_r10_bro_ash|cl_t_home_09_000020'] },
    ] });
  }
  function newReport(gid) {
    const p = byId.get(gid);
    reports.unshift({ gid, date: 'Today', verdict: '', title: `${p.name}, ${POS[p.position].toLowerCase()}, ${p.club}`, draft: true,
      sections: ['Summary', 'Strengths', 'Concerns'].map(name => ({ name, text: '', cites: [] })) });
    openReport = 0; paintReports();
  }
  function paintReports() {
    if (!D) return;
    $('scRList').innerHTML = reports.map((r, i) => `<li><button type="button" class="sc-ritem${i === openReport ? ' on' : ''}" data-rep="${i}">
      <b>${esc(byId.get(r.gid).name)}</b><span class="muted small">${esc(r.date)}${r.draft ? ' · Draft' : ''}</span>${r.verdict ? `<span class="sc-verdict v-${esc(r.verdict.replace(/ /g, ''))}">${esc(r.verdict)}</span>` : ''}</button></li>`).join('')
      || '<li class="muted small">No reports yet.</li>';
    const r = reports[openReport];
    if (!r) { $('scReport').innerHTML = '<p class="muted">Write a report from any player\'s profile, or with New report.</p>'; return; }
    const P = D.profiles[r.gid];
    const cite = (k) => { const m = clipOf.get(k); return m ? `<button type="button" class="sc-cite" data-rplay="${esc(k)}">&#9654; ${esc(F().short(m.title))} <span class="muted">${esc(F().roundName(m))}</span></button>` : ''; };
    if (r.draft) {
      $('scReport').innerHTML = `<div class="pf-bar"><h2>${esc(r.title)}</h2><a class="small-link" href="#scout/player/${esc(r.gid)}">Open profile</a></div>
        ${r.sections.map((s, i) => `<div class="sc-rsec"><label class="pf-field"><span>${esc(s.name)}</span><textarea rows="3" data-rtext="${i}">${esc(s.text)}</textarea></label>
          <div class="sc-cites">${s.cites.map(cite).join('')}<button type="button" class="alt sc-insert" data-rins="${i}">Insert a moment</button></div>
          <div class="mx-picker" data-rpick="${i}" hidden><ol>${F().best(P).map(m => `<li><button type="button" class="link" data-radd="${i}|${esc(F().key(m))}">${esc(F().short(m.title))}</button> <span class="muted small">${esc(F().roundName(m))}</span></li>`).join('')}</ol></div></div>`).join('')}
        <fieldset class="st-choice"><legend>Verdict</legend>${['Sign', 'Keep watching', 'Pass'].map(v => `<label><input type="radio" name="rverdict" value="${v}"${r.verdict === v ? ' checked' : ''}><span>${v}</span></label>`).join('')}</fieldset>
        <div class="pf-addbar"><button type="button" id="scRSave">Save report</button><button type="button" class="alt" id="scRDiscard">Discard</button></div>`;
      return;
    }
    $('scReport').innerHTML = `<div class="pf-bar"><h2>${esc(r.title)}</h2>${r.verdict ? `<span class="sc-verdict v-${esc(r.verdict.replace(/ /g, ''))}">${esc(r.verdict)}</span>` : ''}</div>
      <p class="muted small">By Maya Lindqvist · ${esc(r.date)} · <a href="#scout/player/${esc(r.gid)}">Open profile</a></p>
      <div class="pf-screen sc-rscreen"><video id="scRVideo" controls playsinline preload="none"></video></div><p class="small muted" id="scRNow">Pick a moment to play it.</p>
      ${r.sections.map(s => `<div class="sc-rsec"><h3>${esc(s.name)}</h3><p>${esc(s.text) || '<span class="muted">Nothing written.</span>'}</p><div class="sc-cites">${s.cites.map(cite).join('')}</div></div>`).join('')}`;
  }
  $('scRList').addEventListener('click', (e) => { const b = e.target.closest('[data-rep]'); if (b) { openReport = Number(b.dataset.rep); paintReports(); } });
  $('scReport').addEventListener('input', (e) => { const t = e.target.closest('[data-rtext]'); if (t) reports[openReport].sections[Number(t.dataset.rtext)].text = t.value; });
  $('scReport').addEventListener('change', (e) => { if (e.target.name === 'rverdict') reports[openReport].verdict = e.target.value; });
  $('scReport').addEventListener('click', (e) => {
    const r = reports[openReport], t = e.target;
    const ins = t.closest('[data-rins]'), add = t.closest('[data-radd]'), play = t.closest('[data-rplay]');
    if (ins) { const pk = $('scReport').querySelector(`[data-rpick="${ins.dataset.rins}"]`); pk.hidden = !pk.hidden; return; }
    if (add) { const [i, k] = [add.dataset.radd.split('|')[0], add.dataset.radd.slice(add.dataset.radd.indexOf('|') + 1)]; const s = r.sections[Number(i)]; if (!s.cites.includes(k)) s.cites.push(k); paintReports(); return; }
    if (play) {
      const m = clipOf.get(play.dataset.rplay), v = $('scRVideo');
      if (m && v) { v.src = APP + m.video_url; v.play().catch(() => {}); $('scRNow').textContent = `${F().short(m.title)} · ${F().roundName(m)}`; v.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }
      return;
    }
    if (t.id === 'scRSave') { r.draft = false; r.date = 'Today'; paintReports(); return; }
    if (t.id === 'scRDiscard') { reports.splice(openReport, 1); openReport = 0; paintReports(); }
  });
  $('scNewReport').onclick = () => {
    const first = [...shortlist.keys()].find(g => D.profiles[g] && !reports.some(r => r.gid === g)) || [...shortlist.keys()][0];
    newReport(first);
  };

  // ------------------------------------------------------------------ Messages
  function clipCard(k) {
    const m = clipOf.get(k);
    if (!m) return '';
    return `<div class="mx-clip"><video controls playsinline preload="none" src="${esc(APP + m.video_url)}"></video>
      <div class="mx-cinfo"><span class="reason">${esc(F().REASONS[m.reason] || m.reason)} · ${esc(F().roundName(m))}</span><b>${esc(F().short(m.title))}</b></div></div>`;
  }
  function paintMessages() {
    if (!D) return;
    const unread = convos.reduce((a, c) => a + c.unread, 0);
    $('scUnread').textContent = unread ? String(unread) : '';
    $('scMxList').innerHTML = convos.map(c => {
      const p = byId.get(c.gid), last = c.msgs[c.msgs.length - 1];
      return `<li><button type="button" class="mx-item${c.id === openConvo ? ' on' : ''}" data-convo="${c.id}">
        <span class="mx-av" aria-hidden="true">${esc(p.name.split(' ').map(w => w[0]).join(''))}</span>
        <span class="mx-who"><b>${esc(p.name)}</b><span class="muted small">${esc(POS[p.position])}, ${esc(p.club)}</span>
          <span class="mx-last">${esc(last ? (last.from === 'me' ? 'You: ' : '') + (last.text || 'Sent a moment') : 'New conversation')}</span></span>
        <span class="mx-meta"><span class="muted small">${esc(last ? last.when.split(',')[0] : '')}</span>${c.unread ? `<span class="count">${c.unread}</span>` : ''}</span></button></li>`;
    }).join('');
    const c = convos.find(x => x.id === openConvo), p = byId.get(c.gid);
    $('scMxHead').innerHTML = `<div><b>${esc(p.name)}</b><p class="muted small">${esc(POS[p.position])}, ${esc(p.club)}${shortlist.get(c.gid) ? ` · on your shortlist: ${esc(shortlist.get(c.gid).stage)}` : ''}</p></div>
      <div class="mx-acts"><a class="pf-btn sc-smallbtn" href="#scout/player/${esc(c.gid)}">Profile</a></div>`;
    $('scMxMsgs').innerHTML = c.msgs.map(m => `<li class="mx-msg ${m.from}"><div class="mx-bubble">${m.text ? `<p>${esc(m.text)}</p>` : ''}${(m.clips || []).map(clipCard).join('')}</div>
      <span class="muted small">${esc(m.from === 'me' ? 'You' : p.name.split(' ')[0])} · ${esc(m.when)}</span></li>`).join('')
      || '<li class="muted small mx-blocked">Say hello: players see who you are and your club.</li>';
    const box = $('scMxMsgs'); box.scrollTop = box.scrollHeight;
    $('scNewTo').innerHTML = [...shortlist.keys(), ...D.players.map(x => x.global_id).filter(g => !shortlist.has(g))]
      .map(g => byId.get(g)).filter(Boolean).map(x => `<option value="${esc(x.global_id)}">${esc(x.name)} · ${esc(x.club)}${shortlist.has(x.global_id) ? ' · shortlisted' : ''}</option>`).join('');
  }
  function startConvo(gid) {
    let c = convos.find(x => x.gid === gid);
    if (!c) { c = { id: `s${convos.length + 1}`, gid, unread: 0, msgs: [] }; convos.unshift(c); }
    openConvo = c.id; $('scNewMsgBox').hidden = true;
    location.hash = 'scout/messages';
    setTimeout(() => { document.getElementById('scMx').classList.add('reading'); $('scMxText').focus(); }, 300);
  }
  $('scMxList').addEventListener('click', (e) => {
    const b = e.target.closest('[data-convo]'); if (!b) return;
    openConvo = b.dataset.convo; convos.find(c => c.id === openConvo).unread = 0;
    $('scMx').classList.add('reading'); paintMessages();
  });
  $('scMxBack').onclick = () => $('scMx').classList.remove('reading');
  $('scMxCompose').addEventListener('submit', (e) => {
    e.preventDefault();
    const text = $('scMxText').value.trim(); if (!text) return;
    convos.find(c => c.id === openConvo).msgs.push({ from: 'me', when: 'Just now', text });
    $('scMxText').value = ''; paintMessages(); $('scMxText').focus();
  });
  $('scNewMsg').onclick = () => { $('scNewMsgBox').hidden = !$('scNewMsgBox').hidden; };
  $('scNewCancel').onclick = () => { $('scNewMsgBox').hidden = true; };
  $('scNewStart').onclick = () => { startConvo($('scNewTo').value); paintMessages(); };

  // ------------------------------------------------------------------ Team: Fairhaven's needs and squad
  function paintTeam() {
    const C = D.club, row = D.table.find(t => t.club_id === C.club_id);
    $('scCrest').style.background = `linear-gradient(135deg, ${C.kit.primary} 50%, ${C.kit.secondary} 50%)`;
    $('scClubHead').textContent = C.name;
    $('scClubLine').textContent = `${D.league} ${D.season} · ${C.ground} · ${row.position === 1 ? 'top of the table' : `position ${row.position}`}, ${row.points} points`;
    $('scNeedStat').innerHTML = [...new Set(Object.values(LEAD).flat().concat(['assists', 'key_passes', 'take_ons_won', 'nutmegs', 'clearances']))]
      .map(k => `<option value="${esc(k)}">${esc(label(k))} per 90</option>`).join('');
    paintNeeds();
    $('scSquad').innerHTML = [...C.squad].sort((a, b) => a.kit_number - b.kit_number).map(p => `<li><span class="tm-num">${esc(p.kit_number)}</span>
      <span>${esc(p.name)}</span><span class="muted small">${esc(POS[p.position])}${p.starter ? '' : ' · sub'}</span></li>`).join('');
  }
  function paintNeeds() {
    $('scNeeds2').innerHTML = needs.map((n, i) => {
      const ps = fits(n);
      return `<article class="sc-need"><div class="pf-bar"><h3>${esc(n.title)}</h3><button type="button" class="link" data-dropneed="${i}">Remove</button></div>
        <p class="muted small">${esc(POS[n.pos])}s with ${esc(label(n.stat).toLowerCase())} per 90 better than ${esc(n.pct)}% of the league's ${esc(GROUP[n.pos])} · ${ps.length} fit</p>
        <div class="sc-mini">${ps.slice(0, 6).map(p => `<a href="#scout/player/${esc(p.global_id)}" class="sc-minirow"><span class="sc-shirt" aria-hidden="true">${shirt(p)}</span>
          <span><b>${esc(p.name)}</b> <span class="muted small">${esc(p.club)} · ${esc(headOf(p, n.stat).per90.toFixed(2))} per 90</span></span>${shortlist.get(p.global_id) ? `<span class="sc-stage s-${esc(shortlist.get(p.global_id).stage)}">${esc(shortlist.get(p.global_id).stage)}</span>` : ''}</a>`).join('') || '<p class="muted small">Nobody in the league fits this yet.</p>'}</div></article>`;
    }).join('');
  }
  $('scAddNeed').onclick = () => { $('scNeedForm').hidden = !$('scNeedForm').hidden; if (!$('scNeedForm').hidden) $('scNeedTitle').focus(); };
  $('scNeedCancel').onclick = () => { $('scNeedForm').hidden = true; };
  $('scNeedForm').addEventListener('submit', (e) => {
    e.preventDefault();
    const pos = $('scNeedPos').value, stat = $('scNeedStat').value;
    needs.push({ title: $('scNeedTitle').value.trim() || `A ${POS[pos].toLowerCase()} strong on ${label(stat).toLowerCase()}`, pos, stat, pct: Number($('scNeedPct').value) });
    $('scNeedForm').hidden = true; $('scNeedTitle').value = ''; paintNeeds();
  });
  $('scNeeds2').addEventListener('click', (e) => { const b = e.target.closest('[data-dropneed]'); if (b) { needs.splice(Number(b.dataset.dropneed), 1); paintNeeds(); } });

  // ------------------------------------------------------------------ Settings
  $('scOut').onclick = () => { $('scOutNote').textContent = 'Sandbox: there is no sign-in yet, so there is nothing to sign out of.'; };
})();
