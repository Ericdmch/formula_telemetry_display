# 2021 Azerbaijan — Verstappen

| Source | Type | Used for | Provenance |
| --- | --- | --- | --- |
| [Formula 1 race report](https://www.formula1.com/en/latest/article/perez-beats-vettel-to-baku-victory-after-verstappen-crashes-out-from-lead.aLIxuNGxwBFgZ4Z8OhuRw) | Primary | Tyre failure, main-straight crash, Safety Car then red flag | REAL event facts |
| [RaceFans driver-radio report](https://www.racefans.net/2021/06/08/whos-next-why-are-they-waiting-concern-and-confusion-on-drivers-radios-after-baku-crashes/) | Secondary | Contemporary concern about approaching traffic and neutralization | REAL reported context |
| [FastF1 3.8.3](https://docs.fastf1.dev/core.html) session feed | Official-feed derivative | UTC speed/position, weather, flag, Safety Car, and red-flag timestamps | REAL samples/events; DERIVED normalization and acceleration |

The optional FastF1 cache is local and excluded from Git while upstream data redistribution rights remain unclear. Committed fallback continuous motion is **SIMULATED**, with each field labelled in `scenario.json` and the CSV. T=0 is an approximate speed-trace interpretation. The prior Stroll tyre failure is context only; it is not supplied to the v1 model as a predictive signal.
