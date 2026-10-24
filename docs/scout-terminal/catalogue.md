# The Scout terminal: metric catalogue

What scouts measure (`industry-metrics.md`: 222 entries from FBref, StatsBomb, Opta, Wyscout, American Soccer Analysis,
SkillCorner and FIFA, sources listed there) against what Regista's data can compute (`regista-data.md`: the event contract,
generator, tracks, profiles and vision layer, audited 2026-10-23). Definitions follow FBref's published rules unless noted,
so every number can say where its rule comes from.

**Verdicts:** **Now** = the data has it and nothing adds it up yet (or profiles already do) · **Derive** = new metrics code,
the data supports it · **Generator** = the synthetic league must emit something new · **Vision** = also available when the
match comes from real footage (the vision layer emits 10 of the generator's 28 event types).

## The blocker: players have no ability

The generator gives every player the same probabilities: pass success depends only on distance, pressure and direction
(`synth/generator.py:708`), take-ons are a coin flip, finishing has no skill term, and league players carry only id, name,
kit number, position and starter (`data/season/league.json`). Between two players in the same role, rankings, percentiles,
form and consistency are chance (the audit's split-half test: correlation about 0 within a kit slot). A scouting terminal
needs per-player attributes that drive the generator first; everything below is honest only after that.

## The scout's core ten (what the terminal leads with)

| Metric (per 90 unless noted) | Rule | Verdict | Vision |
|---|---|---|---|
| Non-penalty xG | sum of shot xG, penalties excluded | Now (xG on every shot; no penalties yet, so npxG = xG) | no (no xG) |
| xA / xAG | xG of the shot each key pass led to | Derive (link shot to the pass received) | partly |
| Shot-creating actions | the two offensive actions before each shot | Derive | partly |
| Progressive passes | ≥10 m closer to goal (FBref), or into the box, not from the defending 40% | Derive | yes |
| Progressive carries | same rule for carries | Derive | yes |
| Progressive passes received | completed progressive passes to the player | Derive | yes |
| Take-ons won, take-on % | successful dribbles past an opponent | Now | yes |
| Touches in the box | touches in the attacking penalty area | Derive | no (no touches) |
| Tackles + interceptions, possession-adjusted | per 30 min of opponent possession (Wyscout) | Derive | yes |
| Aerial duel win % | contested headers won | Generator (the sim is 2D) | no |

## Everything else, by category

**Shooting.** Shots, on target, goals, shot accuracy (Now) · xG per shot, goals minus xG (Now; finishing becomes real only
with a finishing attribute) · shot maps with body part (Now) · big chances (Derive, xG ≥ 0.3) · penalties, free-kick shots,
PSxG / xG on target (Generator: no penalties, no shot height).

**Passing and chance creation.** Passes, completion %, by length (Now) · passes under pressure (Now) · key passes, true
definition (Derive: today's stat counts only passes before a goal or save) · xA, SCA, GCA (Derive) · progressive passes and
distance, final-third and box entries, completion by zone, switches, pass networks (Derive) · expected pass completion
(Derive; above-expected needs a passing attribute) · crosses (Now) · through balls (Generator: tagged 0 times in 9,919
passes).

**Possession and progression.** Carries and distance (Now) · progressive carries, carries into the final third and box
(Derive) · take-ons, nutmegs, skill moves (Now) · times dribbled past, ball losses, touches by third (Derive).

**Defending.** Tackles, interceptions, recoveries, pressures, clearances, blocks, fouls, cards (Now) · tackle success %,
pressure regains (ball won within 5 s), ground duels, defensive actions by zone, errors leading to a shot (Derive) · aerial
duels, red cards, offsides (Generator).

**Goalkeeping.** Saves, distribution (Now) · save %, shots on target faced, goals conceded, clean sheets (Derive) · PSxG
minus goals allowed, cross claims, sweeper actions (Generator).

**Possession value.** xT and VAEP (Derive: fit on the season's passes, carries and shots; they will mostly learn the
generator's own rules back until players differ) · EPV, pitch control, off-ball runs (Generator: need 22 players at 10+ Hz).

**Team and style.** Possession %, field tilt, PPDA, sequences, directness, game-state splits, set-piece xG (Derive) ·
home/away splits, set-piece counts (Now) · set-piece delivery (Generator).

**Physical.** Average positions, heat maps (Derive/Now from 1 Hz tracks and events) · distance covered (Derive, but today's
13.8-15.2 km per 90 is not credible) · sprints, top speed, high-speed running (Generator: one 25.2 km/h cap for everyone,
1 Hz, main-camera players only).

**Context.** Per 90, percentiles vs position peers, minimum minutes (Now: percentiles built) · detailed role from the
4-3-3 slot (Derive) · minutes and availability (Generator: no substitutions, everyone plays every minute) · age, height,
foot, nationality, age curves (Generator) · form match by match, consistency (Derive; meaningful once players differ).

## Counts

Of the audit's 79 candidates: 30 Now (18 already in profiles), 35 Derive, 14 Generator, 0 impossible. The real-footage
path carries a subset: no touches, pressures, recoveries, clearances, fouls, set pieces, assists, clock, body part or xG.
