# Contributing to FlagSense

Read [AGENTS.md](AGENTS.md), [architecture](docs/ARCHITECTURE.md), and [data contracts](docs/DATA_CONTRACTS.md) before changing interfaces. Pick a small, independently testable task from the [MVP plan](docs/superpowers/plans/2026-09-26-flagsense-mvp.md). Keep the 12-hour demo objective in view.

Use focused commits with descriptive messages. Suggested branches are `feature/telemetry`, `feature/ml-risk`, `feature/dashboard`, `feature/vision`, `feature/hardware`, and `fix/<description>`. Pull or rebase before large edits when collaborating; coordinate before touching another person's active module. Avoid unrelated rewrites and generated junk.

When a shared schema changes, update its producer, every consumer, [DATA_CONTRACTS.md](docs/DATA_CONTRACTS.md), any saved model schema version, and focused tests in the same change. Keep the seven v1 model columns in their documented order until a deliberate v2 model migration. Put all prototype thresholds in `config.py`.

Run `python -m pytest` before merge and rehearse the headless replay when it exists. Never commit `.env`, API keys, credentials, Streamlit secrets, private uploads, or API response caches. Uploaded images should stay local or temporary. Review `git diff` and `git status` before committing. Do not push without team agreement.
