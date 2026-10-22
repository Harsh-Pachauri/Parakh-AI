# Contributing

Thanks for helping improve AI-Based Viva Voce System. Contributions that fix reproducible bugs, improve security or accessibility, add focused tests, clarify documentation, or make a carefully scoped product improvement are welcome.

This guide reflects the current repository. Backend checks run in CI on Python 3.11; the frontend build runs on Node.js 20. Local development requires Python 3.11 or newer and Node.js 20 or a compatible current release. General product setup is also described in the [README](README.md).

## Before starting

- Read the [README](README.md) and confirm the behavior against the current implementation.
- Search open issues and pull requests before starting work. Check that another contributor is not already addressing the same problem.
- For substantial behavior or architecture changes, open or comment on an issue first to agree on scope and expected behavior.
- Keep each change focused on one issue. Do not include unrelated cleanup or application refactoring.
- Report suspected security vulnerabilities privately. Do not publish exploit details or use production data. If GitHub's private vulnerability reporting is unavailable, contact the repository maintainers through a verified private channel rather than opening a public vulnerability report.

## Development environment

### Prerequisites

- Python 3.11 or newer and `venv`.
- Node.js 20 (the CI version) and npm.
- A Groq API key for live LLM features. It is not needed for mocked unit tests.
- SQLite is the default database. The backend supports async SQLAlchemy database URLs; PostgreSQL requires an appropriate driver installed separately.

### Clone and configure

```powershell
git clone <repository-url>
cd <repository-directory>
Copy-Item .env.example .env
```

Set `GROQ_API_KEY` and a private random `SECRET_KEY` in the root `.env`. Do not commit `.env` or place backend secrets in frontend variables. Keep `.env.example` limited to safe placeholders.

### Install backend dependencies and apply migrations

From the repository root:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
alembic upgrade head
```

### Install frontend dependencies

In a second terminal, from the repository root:

```powershell
cd frontend
npm install
```

### Run the application

Start the backend from `backend\`:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the frontend from `frontend\` in another terminal:

```powershell
npm run dev
```

Open <http://localhost:5173>. The Vite development server proxies `/api` to `http://127.0.0.1:8000`. The API's interactive schema is available at <http://127.0.0.1:8000/docs>.

## Branches and commits

Use a short descriptive branch name, such as `fix/session-question-check`, `security/document-ownership`, `feat/topic-progress`, `test/answer-authorization`, or `docs/contribution-guide`.

Use concise Conventional Commit-style messages where practical, for example:

- `fix: validate session question ownership`
- `security: restrict document access by course owner`
- `test: cover malformed Groq responses`
- `docs: clarify local backend setup`

These naming conventions are recommendations. CI does not currently enforce branch or commit message formats.

## Coding standards

### Backend

- Follow the existing Python style: four-space indentation, type annotations where useful, and Ruff formatting/import conventions.
- Validate API inputs and outputs with Pydantic schemas; use FastAPI dependencies for authentication and role checks.
- Check both role and resource ownership for every read or write involving a teacher-owned course or a candidate-owned session.
- Keep business logic in services when it is shared or non-trivial. Return clear HTTP errors and avoid logging credentials, audio, transcripts, or unnecessary personal data.
- For database changes, update SQLAlchemy models and add an Alembic migration. Keep constraints and indexes consistent with the data invariants they protect.
- Keep Groq as the sole LLM provider. Validate structured model output before it changes interview state or is persisted. Mock Groq in deterministic unit tests.

### Frontend

- Follow the existing React/JavaScript patterns and keep stateful interview behavior in the established hooks/components where practical.
- Provide clear loading, empty, error, and retry states for API-driven screens.
- Preserve keyboard access, visible focus, semantic labels, and responsive layouts when changing UI behavior.
- Do not put API keys, database credentials, or other secrets in `VITE_*` variables; Vite variables are exposed to the browser bundle.
- The frontend currently defines Vite `dev`, `build`, and `preview` scripts. It does not define a lint or automated test script; do not report checks that were not run.

### Dependencies and configuration

- Prefer the standard library or existing dependencies when they meet the need. Explain the reason and maintenance impact of each new dependency.
- Update `backend/pyproject.toml` and `backend/requirements.txt` together when changing runtime dependencies. Update `frontend/package.json` and `frontend/package-lock.json` together for frontend dependencies.
- Update `.env.example`, setup documentation, and migration notes when configuration or persistence behavior changes. Never add real credentials or local data.

## Testing requirements

Add or update focused tests for new behavior and bug fixes. Security changes need negative tests for unauthorized, cross-user, cross-course, or invalid requests as applicable. Persistence changes should verify the database state after the request. Interview changes should cover state transitions and malformed or failed Groq responses using mocks, not live model output.

Run backend checks from `backend\`:

```powershell
ruff check app tests
ruff format --check app tests
alembic upgrade head
pytest
```

Run the frontend production build from `frontend\`:

```powershell
npm run build
```

The backend suite contains a live Groq integration test that runs when `GROQ_API_KEY` is configured and requires external network access. Run it only when you intentionally want a live request. For the deterministic local suite, exclude that test with:

```powershell
pytest -k "not actual_groq_model_integration"
```

The repository does not currently define a frontend test or lint command. For UI changes, manually verify the affected flows in the browser and attach screenshots or a short recording when visual behavior changes. Report test failures accurately; do not omit a failure or imply a check passed when it did not run.

## Pull requests

Keep a pull request focused on its issue and include:

- A concise summary of the problem and change, with a link to the relevant issue.
- The implementation approach and any API, database, migration, or configuration implications.
- The exact checks run and their pass/fail results, including any checks not run and why.
- Known limitations or behavior that remains unverified.
- Screenshots or a short recording for meaningful UI changes; sanitized request/response or persistence evidence for API and database changes.

Use this checklist:

- [ ] The change is limited to the agreed scope.
- [ ] Relevant regression and behavior tests are added or updated.
- [ ] Applicable backend checks and frontend build have been run and reported honestly.
- [ ] Authorization, input validation, and persistence behavior have been considered where relevant.
- [ ] Documentation, `.env.example`, and migrations are updated when needed.
- [ ] No credentials, private transcripts, audio, or production data are included.
- [ ] Required screenshots, test output, or other review evidence is attached.

## Evidence for review

PR evidence should let another developer verify the change without relying on an unsupported claim:

| Change | Evidence to include |
|---|---|
| Backend bug fix | Reproduction steps, regression test, and relevant pytest output; sanitized API response when applicable |
| Security fix | Safe local reproduction, positive and negative authorization tests, regression test, and no sensitive exploit data |
| Frontend change | Before/after screenshot or recording when useful, browser/viewport checked, and build output |
| Database change | Migration result and tests or queries showing the intended persisted state and constraints |
| Performance change | Reproducible before/after measurement under comparable conditions and the measurement method |
| AI workflow change | Mocked representative responses, schema-validation tests, and evidence of correct state after valid and malformed outputs |

Evidence supports review; it does not replace code review or automated checks.

## Review and merge

- CI currently runs Ruff lint/format checks, Alembic migrations, pytest, and the Vite production build. Applicable checks must pass before merge.
- Review should consider correctness, authorization, privacy, maintainability, and regression risk.
- Address review feedback and unresolved comments before merge. Follow any branch protection and approval requirements configured in GitHub; this guide does not assume a fixed number of approvals.
- Do not bypass required checks, branch protection, or repository permissions.

## Security and privacy

- Never commit API keys, passwords, JWTs, private transcripts, audio, or personally identifying test data.
- Use environment variables for local configuration and approved secret-management mechanisms for deployments.
- Minimize candidate data sent to external services or written to logs. Use synthetic or sanitized material in fixtures, screenshots, and public issue/PR descriptions.
- Validate authorization at the backend for every protected resource; hiding a UI control is not an access control.
- Report suspected vulnerabilities privately using the repository's private reporting option when available. Do not test against production or disclose exploitable details publicly before maintainers have addressed the report.

## Documentation and issue quality

Update relevant setup, API, workflow, and configuration documentation when behavior changes. Keep `.env.example` synchronized with supported configuration and explain migration requirements for schema changes.

Issues should describe one reproducible defect or measurable improvement, identify affected code paths, define expected behavior and scope, and list objective acceptance criteria and required validation. Search existing issues first, avoid speculative claims, and do not create issues merely to increase their number.
