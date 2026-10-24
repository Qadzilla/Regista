// The dashboards' per-visitor content (/me, /scout, /players/{id}): messages between scouts and players, the scout's
// shortlist (stages and notes), compare picks, reports, the club's needs, a player's "My details" edits and both
// settings pages. All of it stays in THIS browser (Regista.store, shared/regista.js): nothing here is sent to the
// server. Each piece starts from the seeds below (synthetic people at the Regista League's synthetic clubs) until the
// visitor changes it; "Reset this demo" (Regista.demo.reset) restores the seeds.
//
// ONE conversation store serves both sides: a reply sent from Femi Toure's Messages (/me) is in Maya Lindqvist's inbox
// (/scout) in the same browser, and the reverse. Clips in messages and reports are moment references
// ({ match_id, clip_id, title, reason, round, opponent, t, video_url }): a clip is known by match AND clip id, because
// clip ids repeat across matches (a player is t_away_09 in every away match). video_url is the API's, relative.
//
// Plain script after shared/regista.js; it defines window.Regista.demo and reads no storage until asked.
(function () {
  const R = window.Regista;
  const store = R.store;
  const NOTE = 'Messages, notes and reports are kept in this browser only.';

  // Who writes, on each side. The scout on this browser's Scout dashboard is Maya; the Player dashboard opens on Femi.
  const SCOUT = 'maya';
  const PLAYER = 'pl_bro_09';
  const SCOUTS = {
    maya: { id: 'maya', name: 'Maya Lindqvist', initials: 'ML', role: 'Chief scout', club: 'Fairhaven FC', club_id: 'cl_fairhaven', verified: true },
    tomas: { id: 'tomas', name: 'Tomás Herrera', initials: 'TH', role: 'Scout', club: 'Ashby Athletic', club_id: 'cl_ashby', verified: true },
    priya: { id: 'priya', name: 'Priya Nair', initials: 'PN', role: 'Performance analyst', club: 'Dunmore City', club_id: 'cl_dunmore', verified: false },
  };
  const STAGES = ['Watching', 'Contacted', 'Trial', 'Offer'];
  const VERDICTS = ['Sign', 'Keep watching', 'Pass'];
  const COMPARE_MAX = 3;
  const GID = /^pl_[a-z0-9_]{1,40}$/;

  // ------------------------------------------------------------------ time: seeds are relative to today
  const DAY = 86400000;
  // A time `days` ago at hh:mm local time, so "Today, 09:15" stays today whenever the demo is opened.
  const ago = (days, hhmm) => {
    const [h, m] = hhmm.split(':').map(Number);
    const d = new Date(Date.now() - days * DAY);
    d.setHours(h, m, 0, 0);
    return Math.min(d.getTime(), Date.now() - (days + 1) * 60000);   // never in the future (early in the morning, "today, 10:05" would be)
  };
  // "Today, 09:15", "Yesterday, 18:02", "21 Oct, 18:02"; short: "Today", "Yesterday", "21 Oct".
  function whenText(at, short) {
    if (typeof at !== 'number' || !isFinite(at)) return '';
    const d = new Date(at), now = new Date();
    const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
    const diff = Math.round((day(now) - day(d)) / DAY);
    const date = diff === 0 ? 'Today' : diff === 1 ? 'Yesterday' : d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
    return short ? date : `${date}, ${d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })}`;
  }

  // ------------------------------------------------------------------ moment references
  // ref(moment, match) keeps what a clip card needs; refKey(ref) is "match_id|clip_id".
  const ref = (m, match) => ({
    match_id: m.match_id, clip_id: m.clip_id, title: m.title, reason: m.reason, round: m.round ?? null,
    opponent: (match && match.opponent) || m.opponent || null, t: m.t ?? null, video_url: m.video_url,
  });
  const refKey = (r) => `${r.match_id}|${r.clip_id}`;
  // Femi Toure's moments, as GET /api/players/pl_bro_09 lists them for the league as generated from data/season/league.json.
  // The text that cites them is checked against the league by tests/test_shared_dashboard.py (his three league goals,
  // one a penalty; his take-ons; the shortlist's ranks). Claims are league counts and ranks, so they stay true when his
  // uploaded friendly joins his profile on the live app.
  const CLIPS = {
    r02goal50: { match_id: 'rl_r02_cal_bro', clip_id: 'cl_t_away_09_000008', title: "Femi Toure (9): goal at 50'", reason: 'on_ball_main', round: 2,
                opponent: 'Calder Town', t: 1199.51, video_url: '/api/matches/rl_r02_cal_bro/clips/cl_t_away_09_000008.mp4' },
    r05goal15: { match_id: 'rl_r05_ash_bro', clip_id: 'cl_t_away_09_000008', title: "Femi Toure (9): goal at 15'", reason: 'on_ball_main', round: 5,
                opponent: 'Ashby Athletic', t: 851.87, video_url: '/api/matches/rl_r05_ash_bro/clips/cl_t_away_09_000008.mp4' },
    r06goal47: { match_id: 'rl_r06_bro_eas', clip_id: 'cl_t_home_09_000012', title: "Femi Toure (9): goal at 47'", reason: 'on_ball_main', round: 6,
                opponent: 'Eastwick United', t: 1004.11, video_url: '/api/matches/rl_r06_bro_eas/clips/cl_t_home_09_000012.mp4' },
    r06takeon3: { match_id: 'rl_r06_bro_eas', clip_id: 'cl_t_home_09_000003', title: "Femi Toure (9): take-on at 3'", reason: 'on_ball_main', round: 6,
                opponent: 'Eastwick United', t: 130.82, video_url: '/api/matches/rl_r06_bro_eas/clips/cl_t_home_09_000003.mp4' },
    r09takeon2: { match_id: 'rl_r09_bro_dun', clip_id: 'cl_t_home_09_000003', title: "Femi Toure (9): take-on at 2'", reason: 'on_ball_main', round: 9,
                opponent: 'Dunmore City', t: 86.49, video_url: '/api/matches/rl_r09_bro_dun/clips/cl_t_home_09_000003.mp4' },
  };

  // ------------------------------------------------------------------ the seeds
  // Built on each call (times are relative to now); store.get hands back a copy of whatever it returns.
  function seeds() {
    return {
      // Scouts start conversations; players reply, mute or block. unread counts per side.
      conversations: [
        { id: 'cv_maya_bro_09', scout: 'maya', player: 'pl_bro_09', player_name: 'Femi Toure', unread: { player: 1, scout: 0 }, muted: false, blocked: false,
          msgs: [
            { from: 'scout', at: ago(2, '18:02'), text: 'Hi Femi, we have been watching you closely. Three league goals, more than anyone else in the league, stand out. Could you send a couple of your finishes?' },
            { from: 'player', at: ago(2, '19:40'), text: 'Thanks Maya. Here are two from this season.', clips: [CLIPS.r05goal15, CLIPS.r06goal47] },
            { from: 'scout', at: ago(0, '09:15'), text: 'The first one is exactly what we look for: struck from outside the box. Are you free for a call on Thursday?' },
          ] },
        { id: 'cv_tomas_bro_09', scout: 'tomas', player: 'pl_bro_09', player_name: 'Femi Toure', unread: { player: 1, scout: 0 }, muted: false, blocked: false,
          msgs: [
            { from: 'scout', at: ago(0, '08:30'), text: 'Your goal against Eastwick in round 6 caught our eye. Do you have footage from friendlies too? We would like to see more of you.' },
          ] },
        { id: 'cv_priya_bro_09', scout: 'priya', player: 'pl_bro_09', player_name: 'Femi Toure', unread: { player: 0, scout: 0 }, muted: false, blocked: false,
          msgs: [
            { from: 'scout', at: ago(5, '14:10'), text: 'Your strike from distance against Ashby in round 5 was well taken. Keep adding matches, it helps us see more of you.' },
            { from: 'player', at: ago(5, '16:55'), text: 'Will do, I have a friendly coming up and will upload it.' },
          ] },
        { id: 'cv_maya_eas_03', scout: 'maya', player: 'pl_eas_03', player_name: 'Gino Mensah', unread: { player: 0, scout: 1 }, muted: false, blocked: false,
          msgs: [
            { from: 'scout', at: ago(3, '11:00'), text: 'Gino, Fairhaven would like to make you an offer for next season. The details are attached in our club portal.' },
            { from: 'player', at: ago(0, '10:05'), text: 'Thank you, that means a lot. I am talking it through with my family. Could we speak early next week?' },
          ] },
        { id: 'cv_maya_dun_06', scout: 'maya', player: 'pl_dun_06', player_name: 'Farid Vargas', unread: { player: 0, scout: 0 }, muted: false, blocked: false,
          msgs: [
            { from: 'scout', at: ago(7, '15:20'), text: 'Farid, your trial is booked for the week of 9 November. Bring boots for grass and artificial turf.' },
            { from: 'player', at: ago(7, '17:02'), text: 'Great, see you then.' },
          ] },
      ],
      // Maya's shortlist: a stage and a private note per player, in the order she added them.
      shortlist: {
        pl_bro_09: { stage: 'Contacted', note: 'Top scorer in the league: three league goals in three different matches (one a penalty), the most per 90 among the league\'s regular forwards. Call booked for Thursday.', at: ago(9, '10:00') },
        pl_ash_10: { stage: 'Watching', note: 'Beats his man from the number 10: third among midfielders for take-ons won per 90. Check his work without the ball.', at: ago(8, '10:00') },
        pl_ash_09: { stage: 'Watching', note: 'Gets his shots away: third among the league\'s regular forwards for shots per 90. Watch more of his movement off the ball.', at: ago(8, '11:00') },
        pl_dun_06: { stage: 'Trial', note: 'Keeps the ball moving from deep: second among midfielders for passes per 90. Trial week booked for 9 November.', at: ago(7, '15:00') },
        pl_eas_03: { stage: 'Offer', note: 'Creates from full-back: fifth among defenders for key passes per 90 (one season of key passes is mostly noise). Offer sent, waiting for his answer.', at: ago(3, '11:00') },
      },
      compare: [],
      // Reports: sections of text, each citing moments that play.
      reports: [
        { id: 'rp_bro_09_1', gid: 'pl_bro_09', author: 'maya', at: ago(1, '17:30'), verdict: 'Sign', draft: false,
          title: 'Femi Toure, forward, Brookfield Rovers',
          sections: [
            { name: 'Summary', text: "The league's top scorer: three league goals, each in a different match (one a penalty), the most per 90 of its 18 regular forwards.",
              cites: [CLIPS.r02goal50, CLIPS.r05goal15, CLIPS.r06goal47] },
            { name: 'Strengths', text: 'Shoots often and hits the target: the most shots on target of the league\'s forwards, in total and per 90. Scores from distance and from the penalty spot.',
              cites: [CLIPS.r05goal15, CLIPS.r02goal50] },
            { name: 'Concerns', text: 'Won one of his seven take-ons in league matches: we would want more from him one against one; watch him against a deep block.',
              cites: [CLIPS.r06takeon3, CLIPS.r09takeon2] },
          ] },
      ],
      // Fairhaven's needs: each lists the league's players who fit, from their numbers (stat per 90, percentile).
      needs: [
        { id: 'nd_1', title: 'A forward who scores', pos: 'FW', stat: 'goals', pct: 75 },
        { id: 'nd_2', title: 'A midfielder who wins the ball back', pos: 'MF', stat: 'recoveries', pct: 75 },
        { id: 'nd_3', title: 'A defender who reads the game', pos: 'DF', stat: 'interceptions', pct: 75 },
      ],
      // "My details" edits, per player: { name, position, kit_number, foot, height, bio }. None until a player saves.
      details: {},
      'settings.player': {
        email: 'femi.toure@regista-league.example', see: 'everyone', message: 'verified',
        notify: { message: true, upload: true, question: true, weekly: false },
        footage: { process: true, show: true, improve: false },
      },
      'settings.scout': {
        email: 'maya.lindqvist@fairhaven-fc.example', privacy: 'club',
        notify: { reply: true, match: true, fit: true, weekly: false },
      },
    };
  }
  const seed = (name) => seeds()[name];
  const read = (name) => store.get(name, seed(name));
  const write = (name, value) => store.set(name, value);

  // ------------------------------------------------------------------ conversations
  const conversations = () => { const v = read('conversations'); return Array.isArray(v) ? v : seed('conversations'); };
  const saveConversations = (list) => write('conversations', list);
  const byLatest = (a, b) => last(b) - last(a);
  const last = (c) => (c.msgs.length ? c.msgs[c.msgs.length - 1].at : c.at || 0);
  // A player's inbox (every scout who wrote to them) and a scout's (every player they wrote to), newest first.
  const forPlayer = (gid) => conversations().filter((c) => c.player === gid).sort(byLatest);
  const forScout = (id = SCOUT) => conversations().filter((c) => c.scout === id).sort(byLatest);
  const conversation = (id) => conversations().find((c) => c.id === id) || null;
  function update(id, fn) {
    const list = conversations();
    const c = list.find((x) => x.id === id);
    if (!c) return null;
    fn(c);
    saveConversations(list);
    return c;
  }
  // The conversation between a scout and a player, started (empty) if there is none yet. Idempotent.
  function startConversation(scoutId, gid, playerName) {
    if (!SCOUTS[scoutId] || !GID.test(String(gid))) return null;
    const list = conversations();
    let c = list.find((x) => x.scout === scoutId && x.player === gid);
    if (!c) {
      c = { id: `cv_${scoutId}_${gid.slice(3)}`, scout: scoutId, player: gid, player_name: playerName || '', at: Date.now(),
            unread: { player: 0, scout: 0 }, muted: false, blocked: false, msgs: [] };
      list.unshift(c);
      saveConversations(list);
    } else if (playerName && !c.player_name) {
      c.player_name = playerName;
      saveConversations(list);
    }
    return c;
  }
  // from: 'scout' or 'player'. A blocked conversation takes nothing from the scout. Clips: moment references.
  function send(id, from, text, clips) {
    const body = String(text || '').trim().slice(0, 2000);
    const refs = (clips || []).filter((r) => r && r.match_id && r.clip_id).map((r) => ref(r));
    if (!body && !refs.length) return null;
    const c = conversation(id);
    if (!c || (from === 'scout' && c.blocked) || (from !== 'scout' && from !== 'player')) return null;
    return update(id, (x) => {
      x.msgs.push({ from, at: Date.now(), text: body, clips: refs });
      const other = from === 'scout' ? 'player' : 'scout';
      x.unread = x.unread || { player: 0, scout: 0 };
      if (!(other === 'player' && x.muted)) x.unread[other] = (x.unread[other] || 0) + 1;
    });
  }
  const markRead = (id, side) => update(id, (x) => { x.unread = { ...(x.unread || {}), [side]: 0 }; });
  const setMuted = (id, v) => update(id, (x) => { x.muted = !!v; });
  const setBlocked = (id, v) => update(id, (x) => { x.blocked = !!v; });
  // Unread messages: unread('player', 'pl_bro_09') or unread('scout', 'maya'). Blocked and muted threads count none.
  const unread = (side, who) => conversations()
    .filter((c) => (side === 'player' ? c.player === who && !c.blocked && !c.muted : c.scout === who))
    .reduce((n, c) => n + ((c.unread && c.unread[side]) || 0), 0);

  // ------------------------------------------------------------------ shortlist and compare
  const OLD_SHORTLIST = 'regista-scout-shortlist';  // the Scout view's shortlist before the dashboards
  function shortlist() {
    const have = store.get('shortlist', null);
    if (have && typeof have === 'object') return have;
    // First visit: the seeds, plus anyone the old Scout view's shortlist held (as Watching).
    const list = seed('shortlist');
    try {
      const old = JSON.parse(localStorage.getItem(OLD_SHORTLIST) || '[]');
      if (Array.isArray(old)) {
        for (const x of old) {
          if (x && GID.test(String(x.global_id)) && !list[x.global_id]) list[x.global_id] = { stage: 'Watching', note: '', at: Date.now() };
        }
        if (old.length) write('shortlist', list);
      }
    } catch (e) { /* storage blocked or the old value unreadable: the seeds stand */ }
    return list;
  }
  const saveShortlist = (s) => write('shortlist', s);
  const onShortlist = (gid) => Object.prototype.hasOwnProperty.call(shortlist(), gid);
  // setStage(gid, 'Trial') adds or moves a player; setStage(gid, '') takes them off (and out of compare).
  function setStage(gid, stage) {
    if (!GID.test(String(gid))) return;
    const s = shortlist();
    if (!stage) { delete s[gid]; setCompare(compare().filter((g) => g !== gid)); }
    else if (STAGES.includes(stage)) s[gid] = { note: '', at: Date.now(), ...(s[gid] || {}), stage };
    saveShortlist(s);
  }
  // A note keeps the player on the shortlist (Watching if they were not on it).
  function setNote(gid, note) {
    if (!GID.test(String(gid))) return;
    const s = shortlist();
    s[gid] = { stage: 'Watching', at: Date.now(), ...(s[gid] || {}), note: String(note || '').slice(0, 2000) };
    saveShortlist(s);
  }
  const compare = () => { const v = read('compare'); return Array.isArray(v) ? v.filter((g) => GID.test(String(g))).slice(0, COMPARE_MAX) : []; };
  const setCompare = (list) => write('compare', [...new Set(list)].filter((g) => GID.test(String(g))).slice(0, COMPARE_MAX));
  // In or out of compare; returns whether the player is now in it (false when compare is full).
  function toggleCompare(gid) {
    const c = compare();
    if (c.includes(gid)) { setCompare(c.filter((g) => g !== gid)); return false; }
    if (c.length >= COMPARE_MAX || !GID.test(String(gid))) return false;
    setCompare([...c, gid]);
    return true;
  }

  // ------------------------------------------------------------------ reports
  const reports = () => { const v = read('reports'); return Array.isArray(v) ? v : seed('reports'); };
  const saveReports = (list) => write('reports', list);
  // The player's open draft, or a new one (Summary, Strengths, Concerns). Idempotent while a draft is open.
  function draftReport(gid, title) {
    if (!GID.test(String(gid))) return null;
    const list = reports();
    let r = list.find((x) => x.gid === gid && x.draft);
    if (!r) {
      r = { id: `rp_${gid.slice(3)}_${Date.now().toString(36)}`, gid, author: SCOUT, at: Date.now(), verdict: '', draft: true,
            title: title || '', sections: ['Summary', 'Strengths', 'Concerns'].map((name) => ({ name, text: '', cites: [] })) };
      list.unshift(r);
      saveReports(list);
    }
    return r;
  }
  function saveReport(r) {
    const list = reports();
    const i = list.findIndex((x) => x.id === r.id);
    if (i < 0) list.unshift(r); else list[i] = r;
    saveReports(list);
  }
  const dropReport = (id) => saveReports(reports().filter((x) => x.id !== id));

  // ------------------------------------------------------------------ needs, details, settings
  const needs = () => { const v = read('needs'); return Array.isArray(v) ? v : seed('needs'); };
  const saveNeeds = (list) => write('needs', list);
  const details = (gid) => { const all = read('details') || {}; return all[gid] || null; };
  function saveDetails(gid, d) {
    const all = read('details') || {};
    if (d) all[gid] = d; else delete all[gid];
    write('details', all);
  }
  const settings = (side) => read(`settings.${side === 'scout' ? 'scout' : 'player'}`);
  const saveSettings = (side, obj) => write(`settings.${side === 'scout' ? 'scout' : 'player'}`, obj);

  // Restore every seed: the dashboards' "Reset this demo". The old Scout view's shortlist goes too, or its players would
  // be merged back into the restored shortlist on the next read.
  const reset = () => {
    store.reset();
    try { localStorage.removeItem(OLD_SHORTLIST); } catch (e) { /* storage blocked: nothing kept to remove */ }
  };

  R.demo = {
    NOTE, SCOUT, PLAYER, SCOUTS, STAGES, VERDICTS, COMPARE_MAX,
    seeds, whenText, ref, refKey,
    conversations, saveConversations, forPlayer, forScout, conversation, startConversation, send, markRead, setMuted, setBlocked, unread,
    shortlist, saveShortlist, onShortlist, setStage, setNote, compare, setCompare, toggleCompare,
    reports, saveReports, draftReport, saveReport, dropReport,
    needs, saveNeeds, details, saveDetails, settings, saveSettings,
    reset,
  };
})();
