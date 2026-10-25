# Architecture — Română B1

## Scope
Milestone 1 is a text-only Telegram tutor for Romanian B1 (ILR by default). Russian explanations, Romanian practice, teaching/exam modes. A short diagnostic covers reading, grammar, vocabulary and writing; listening/speaking remain unassessed. No official pass prediction. Calendar, speech and Anki are outside this milestone.

## Modular monolith
Python 3.12, aiogram 3 transport, FastAPI operational API, Pydantic 2 contracts, SQLAlchemy 2 + Alembic + PostgreSQL persistence. OpenRouter is the only implemented model adapter. Separate bot/API processes share the database and the same Learning Core. Business rules never live in Telegram handlers.

- `app/config.py`: environment configuration, secret-safe validation.
- `app/db.py`, `app/models.py`: transactions, relational integrity and per-user ownership.
- `app/schemas.py`: strict model output and domain schemas.
- `app/llm.py`: role-based model selection, bounded context, validated JSON, retries and usage.
- `app/services/`: TutorService, PlannerService, MistakeTracker, scheduling and registration.
- `app/bot.py`: commands, inline actions and durable conversation routing.
- `app/api.py`: health/readiness; no unauthenticated personal-data endpoints.
- `app/ports.py`: Calendar/STT/TTS/audio-analysis interfaces only.
- `alembic/`, `tests/`, `docs/`: migrations, unit/integration/adapter tests and evidence.

## State and integrity
Persist users, profiles, exam targets, plans, lessons, tasks, attempts, mistakes, progress, conversation sessions and model usage. Persist message deduplication and reschedule history as well. All reads/writes are scoped to the authenticated Telegram sender. Unique message keys prevent duplicate learning effects. Durable current lesson/task IDs support restart recovery. Concurrent operations for a user serialize using a database lock (PostgreSQL), with unique constraints as defense in depth. Commit before acknowledging successful processing; external-send failures must not lose learning state. Never hold a global lock across users.

## Pedagogy
Plans combine available weekly time, timezone, preferred slots, target date, self-reported level and diagnostic weaknesses. Dependencies and measurable mastery criteria are explicit. Lessons draw from saved plan and unresolved mistakes. Uncertain assessments do not mark mastery or invent errors. Accept valid alternatives, reduce hints progressively, collect exam answers before feedback. Each significant error affects follow-up work; repeated evidence determines resolution. Scheduling records each move, preserves the target date and warns if the workload no longer fits.

## Model boundary
Use separate configurable model roles, token limits, compact prior-session memory and current task context. Treat learner text as untrusted data. Validate every structured response and task identity. Retry temporary HTTP failures with bounded backoff; report missing credentials and invalid output clearly. Store actual provider usage/cost when supplied; unknown cost stays unknown. Never log secrets or full request bodies. Model grading is formative, not official certification.

## Deployment and verification
Docker Compose provides PostgreSQL, migrations, API and bot. FastAPI readiness queries the database. Use frozen dependency resolution. Unit tests cover teaching/planning/scheduling; DB tests cover isolation, constraints, duplicate delivery and restart recovery. Mock OpenRouter tests prove adapter behavior, not live API access. Run PostgreSQL integration and a representative complete registration → diagnostic → plan → lesson → correction flow. Document exact external-service limitations.
