# 2024 Azerbaijan — Pérez/Sainz

| Source | Type | Used for | Provenance |
| --- | --- | --- | --- |
| [Formula 1 race report](https://www.formula1.com/en/latest/article/its-very-disappointing-sainz-and-perez-give-their-views-on-dramatic-late.33pViZ5hLOZkAQcePX3WnC) | Primary | Lap 50 collision and VSC outcome | REAL event facts |
| [RaceFans report](https://www.racefans.net/2024/09/16/f1-drivers-surprised-race-control-waited-before-deploying-vsc-after-sainz-perez-crash/) | Secondary | Debris, view toward sun, reported concern about timing | REAL reported context |
| [FIA race-control messages](https://www.fia.com/sites/default/files/2024_17_aze_f1_r0_timing_raceracecontrolmessages_v01.pdf) | Primary | Yellow and VSC sequence, minute-level public cross-check | REAL event facts |
| [FastF1 3.8.3](https://docs.fastf1.dev/core.html) session feed | Official-feed derivative | UTC car speed and position samples, weather, race-control message timestamps | REAL speed/weather/messages; DERIVED relative time, coordinate conversion, acceleration, track proxy |

The optional online preparation script writes processed FastF1 files locally. They are excluded from Git because upstream F1 data redistribution rights are not established. The committed fallback reconstruction uses **SIMULATED** continuous speed, position, and acceleration; these values must never be described as historical telemetry. `scenario.json` includes sourced control event timestamps; T=0 is an approximate onset interpreted from the speed trace, so relative delays inherit that uncertainty. The local race-control feed has more precise timestamps than the public FIA PDF's minute display.
