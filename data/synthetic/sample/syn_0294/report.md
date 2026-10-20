# Synthetic realism report: syn_0294

Generator profile: **demo**. The demo profile is deliberately dense so a 3-minute sample fills a clip reel; its rates are expected to sit above the bands. 

Simulated minutes: 3.02

Norms: Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth.

| Metric | Value | Band | Verdict | Note |
|---|---|---|---|---|
| passes_per90 | 894.0 passes | 800.0–1100.0 | in band | attempted passes and crosses, both teams |
| pass_completion | 0.833 ratio | 0.78–0.87 | in band | completed / attempted |
| shots_per90 | 59.6 shots | 20.0–32.0 | high | both teams |
| goals_per90 | 29.8 goals | 2.2–3.6 | high | both teams |
| xg_per_shot | 0.153 xG | 0.08–0.13 | high | mean expected goals per shot |
| tackles_per90 | 119.2 tackles | 28.0–45.0 | high | both teams |
| interceptions_per90 | 149.0 interceptions | 14.0–30.0 | high | both teams |
| take_ons_per90 | 149.0 take-ons | 28.0–50.0 | high | attempted dribbles past a defender |
| nutmegs_per90 | 59.6 nutmegs | 0.5–3.0 | high | rarely reported; broadcast estimate |
| fouls_per90 | 0.0 fouls | 18.0–28.0 | low | both teams |
| corners_per90 | 0.0 corners | 8.0–13.0 | low | both teams |
| throw_ins_per90 | 29.8 throw-ins | 35.0–55.0 | low | both teams |
| possession_mean_s | 2.53 seconds | 1.5–4.5 | in band | mean time one player holds the ball |

**3 of 13 metrics in band.**

Diagnostics (no band): replays_per_goal=3.0, tracks_kit_number_share=0.733, minutes=3.02, possession_changes_per90=357.6, carries_per90=596.0, pressures_per90=327.8
