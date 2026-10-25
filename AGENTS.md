# Codex team
- Architect coordinates architecture, integration and acceptance; requested model gpt-6-astra / high. Never claim a live model switch without evidence.
- Delegate routine implementation to Coder (gpt-6.1-sol / medium), independent review to Reviewer (gpt-6.1-sol / high), read-only research to Explorer/researcher (gpt-6-luna / high).
- Use native Codex subagents, at most three concurrent children. Do not let coders edit overlapping files. Reviewer reports findings without editing.
- Follow MASTER_PROMPT.md and ARCHITECTURE.md. Target official Romanian B1; all learning behavior goes through Learning Core. Coordinate architectural changes.
- Each completed module needs meaningful tests. Report failures, skips and untested integrations honestly.
- Implement only Milestone 1. Calendar, voice and Anki implementations wait for later milestones.
- Work in this existing isolated checkout; no worktrees unless requested. Keep keys out of Git and logs.
