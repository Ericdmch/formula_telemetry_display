# Judge demo runbook

**Status:** synthetic and four historical dashboard replays are available offline. The synthetic scenario remains the default. Historical fallback motion is simulated; locally prepared FastF1 speed/position feeds can replace it for the two Azerbaijan incidents. Both modes are decision support demonstrations.

| Replay time | Show and say | Expected recommendation |
| --- | --- | --- |
| 0–10 s | Multiple cars at race speed; no detected incident. Point to the track map and speed trace. | GREEN |
| 10–13 s | Car #12 decelerates from roughly 210 → 130 → 40 → 0 km/h. Point to the measured acceleration and detector event. | Candidate event; do not overstate it as a crash |
| 13–16 s | Car #12 remains stopped on/near the racing-line proxy. | YELLOW immediately; a prolonged stop can escalate to VSC |
| 16–20 s | Car #7 approaches near 190–210 km/h. Show along-track gap, closing speed, and sector. | SAFETY CAR recommendation as fast traffic closes |
| End | Read the actual evidence reasons, model source, and rule ID. If connected, trigger the optional display and show green → yellow → Safety Car. State that race control makes the final decision. | Recommendation only |

The image should be used to extract observable facts: vehicle on track, apparent blockage, debris, smoke/fire, wet surface, and confidence. Do not ask the image model for a flag. If those facts are unavailable, show that they are unavailable and continue with telemetry and local context. The example 92% risk score is illustrative; the live score comes from the pipeline and must never be hard-coded into the UI.

## Preflight

1. Activate the local Python environment; run `python -m pytest`.
2. Run `python -m scripts.run_demo` and confirm the synthetic replay's ordered transitions.
3. Start `streamlit run app.py`; test Start, Pause, Reset, and a second identical replay.
4. Select **2024 Azerbaijan — Pérez/Sainz**. Confirm the data-quality label says whether the local FastF1 cache or the simulated fallback is active. Show the separate actual and FlagSense lanes and the `SOURCES.md` path. The first measured-data cache is built with `python scripts/fetch_historical_scenarios.py --scenario 2024_azerbaijan_perez_sainz` during online preparation only.
5. Select 2021 Azerbaijan, 2022 Canada, and 2024 Qatar. Compare the escalation timing with the separate actual-control timeline.
6. If presenting hardware, connect USB, confirm the configured serial port, and test each display token. Keep the software-only run ready.

## Fallbacks

| Failure | Demo action |
| --- | --- |
| Internet or vision API unavailable | Use committed labelled motion reconstruction; omit image evidence unless a configured provider or source-labelled cached visual JSON exists. No live service is required. |
| Model missing/incompatible | Continue with `rules_fallback`; show its label and avoid calling its display values ML probabilities. |
| Hardware disconnected | Continue the dashboard; describe serial output as optional and show the recommendation on screen. |
| Streamlit fails | Use `python -m scripts.run_demo` for the synthetic replay, or `load_scenario(id).replay()` in Python for a historical replay. |
| Telemetry/track asset missing | Restore the committed demo assets. If no valid telemetry exists, show DATA_UNAVAILABLE rather than GREEN. |

All example thresholds are prototype values, not official FIA rules. Do not imply an autonomous or certified safety decision.
