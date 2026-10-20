# Synthetic realism report: profile 'realistic', seeds [21, 22, 23, 24, 25, 26, 27, 28], 30 min each

Generator profile: **realistic**. The realistic profile is tuned to sit inside the bands over a full match. 

Simulated minutes: 240.54

Norms: Approximate Premier League season averages, both teams combined, per 90 minutes (FBref/Opta, 2021-24). Sanity bands, not ground truth.

| Metric | Value | Band | Verdict | Note |
|---|---|---|---|---|
| passes_per90 | 1005.0 passes | 800.0–1100.0 | in band | attempted passes and crosses, both teams |
| pass_completion | 0.790 ratio | 0.78–0.87 | in band | completed / attempted |
| shots_per90 | 27.7 shots | 20.0–32.0 | in band | both teams |
| goals_per90 | 2.99 goals | 2.2–3.6 | in band | both teams |
| xg_per_shot | 0.117 xG | 0.08–0.13 | in band | mean expected goals per shot |
| tackles_per90 | 32.9 tackles | 28.0–45.0 | in band | both teams |
| interceptions_per90 | 26.2 interceptions | 14.0–30.0 | in band | both teams |
| take_ons_per90 | 47.1 take-ons | 28.0–50.0 | in band | attempted dribbles past a defender |
| nutmegs_per90 | 1.87 nutmegs | 0.5–3.0 | in band | rarely reported; broadcast estimate |
| fouls_per90 | 24.7 fouls | 18.0–28.0 | in band | both teams |
| corners_per90 | 10.9 corners | 8.0–13.0 | in band | both teams |
| throw_ins_per90 | 52.4 throw-ins | 35.0–55.0 | in band | both teams |
| possession_mean_s | 2.57 seconds | 1.5–4.5 | in band | mean time one player holds the ball |

**13 of 13 metrics in band.**

Diagnostics (no band): replays_per_goal=7.5, minutes=240.54, possession_changes_per90=268.6, carries_per90=478.5, pressures_per90=198.7
