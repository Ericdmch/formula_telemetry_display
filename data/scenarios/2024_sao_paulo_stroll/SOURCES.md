# 2024 São Paulo qualifying — Stroll

| Source | Type | Used for | Provenance |
| --- | --- | --- | --- |
| [Formula 1 qualifying report](https://www.formula1.com/en/latest/article/norris-beats-russell-and-tsunoda-to-pole-position-in-sao-paulo-amid-five-red.2PERamLqTYyD4M7zI55X0n.2PERamLqTYyD4M7zI55X0n) | Primary | Wet qualifying, Q2 crash and red flag | REAL event facts |
| [Motorsport.com explanation](https://www.motorsport.com/f1/news/explained-the-brazilian-gp-red-flag-delay-that-red-bull-claims-cost-verstappen/10670213/) | Secondary, reporting FIA explanation | Local yellows, assessment of whether car could return, approximate delay | REAL reported context |
| [FastF1 3.8.3](https://docs.fastf1.dev/core.html) session feed | Official-feed derivative | Speed/position, weather, yellow and red timestamps | REAL samples/events; DERIVED normalization and acceleration |

The Motorsport.com article describes a roughly **40-second** red-flag delay, whereas the FastF1 message timestamp is **55.5 seconds after our approximate telemetry onset**. The anchors differ. We show the feed events and label T=0 approximate; we do not silently reconcile these into a fabricated exact delay. FastF1 cache files are local and excluded from Git while upstream redistribution rights remain unclear. Committed fallback motion is **SIMULATED**.
