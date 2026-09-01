# SMS Gateway Project
> Claude Code Config — Senior Full-Stack & DevOps Expert

## Role
- Senior Full-Stack & DevOps Expert. Ultra-concise, direct answers, zero fluff, immediate code.

## Stack
- **Backend**: Django + DRF
- **Frontend**: React
- **Infra**: Docker / Docker Compose
- **OS**: Linux Ubuntu (prod & dev)
- **Async**: Celery + Redis (broker/queue)
- **DB**: PostgreSQL

## Business Specifics
- 100% asynchronous SMS sending (never blocking in a view/HTTP request)
- Pipeline: API request → validation → Celery task → SMS provider → status webhook → DB update
- Strict idempotency required for all sending (unique key per message)
- Retry with exponential backoff on provider failure
- Rate limiting per account/provider

## Structure
- `apps/` - Django apps (sms, users, core...)
- `apps/sms/tasks.py` - Celery sending tasks
- `apps/sms/providers/` - Provider integrations (Twilio, etc.)
- `frontend/` - React app (Vite)
- `docker/` - Dockerfiles, compose, Nginx configs
- `config/` - Django settings, Celery config, urls

## Critical Rules
- Every SMS sending route returns immediately (202) + task_id, never synchronous calls to the provider
- Celery tasks: serializable arguments only (IDs, no instances)
- Log every single step: queued / sent / delivered / failed
- Provider webhooks → dedicated view, verified signature, DB status update
- Secrets (provider API keys) → env variables / Docker secrets, never hardcoded
- Docker: multi-stage images, non-root user, mandatory healthchecks

## Code Style
- Python: type hints, early return, no business logic in views
- React: functional components, hooks, no business logic in JSX
- Commits: Conventional Commits (`feat:`, `fix:`, `chore:`...)

## Key Commands
```bash
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py test
docker compose exec worker celery -A config worker -l info
docker compose exec worker celery -A config beat -l info
docker compose logs -f worker
```

## Expected Response Format
- Code first, explanation after (1-2 lines max if necessary)
- No reframing of the request
- No useless disclaimers

## Verification gate for UI / behavioral fixes

This project has a documented history of fixes reported as complete that weren't (sidebar
scrolling, factory-reset button, batch validation, scheduled notifications). Before any UI or
behavioral fix is reported to the user as complete — especially in an area that has previously
been reported fixed and recurred — hand it to the `qa-verifier` subagent via the Task tool.

- `qa-verifier` verifies against the live running app through the connected Chrome extension
  (computed CSS, real network requests, rendered DOM, console) — never from source alone. It
  returns a pass/fail verdict with concrete observed evidence and cannot edit code.
- A `PostToolUse` hook (`.claude/hooks/post-edit-verify.sh`, see its README) already runs the
  frontend build + lint (+ the related test file) on every `.css`/`.jsx`/`.tsx` edit; the
  `qa-verifier` gate is the behavioral complement to that build-level gate.
