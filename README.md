

cd backend# CivicWatch — Anambra Civic Reporting Platform

A full-stack **development foundation** for the agreed CivicWatch architecture: social-style public feed, authenticated citizen accounts, structured civic reports, report support and comments, personal report tracking, role-based government queues, case assignment/status history, and analytics.

> **Important:** This is a runnable project foundation, not a certified production government service. Before real public launch, complete security review, privacy/legal review, moderation operations, government agency mapping, backup/restore testing, accessibility/performance testing, and deployment hardening. The seeded/demo government account must never be used in production.

## Stack
- Frontend: Next.js App Router, TypeScript, simple responsive CSS
- Backend: FastAPI, SQLAlchemy, JWT bearer authentication, password hashing
- Database: PostgreSQL via Docker Compose; SQLite fallback for local backend-only development
- File uploads: local development directory (replace with private object storage for production)

## Run with Docker (recommended)
1. Install Docker Desktop.
2. In this directory, copy `.env.example` to `.env` and replace every secret.
3. Run:
   ```bash
   docker compose up --build
   ```
4. Open the citizen interface at `http://localhost:3000` and API docs at `http://localhost:8000/docs`.

The backend creates tables and seeds categories plus one demo government user on first startup:
- Email: `admin@civicwatch.ng`
- Password: `ChangeThisDemoPassword123!`
- Role: `state_admin`

Change these credentials immediately. Demo credentials are for local demonstration only.

## Run without Docker
Backend (Python 3.11+ recommended):
```bash
cd backend
python -m venv .venv
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
# Set DATABASE_URL and SECRET_KEY in your environment if needed

```
Frontend (Node.js 20+):
```bash
cd frontend
npm install
npm run dev
```
Set `NEXT_PUBLIC_API_URL=http://localhost:8000` in `frontend/.env.local` if needed.

## Implemented
- Register/login; password hashing; signed JWT tokens.
- Public feed of public civic reports.
- Registered citizens can create reports, support/unsupport reports, comment, and view their own reports.
- Categories and category-specific detail fields stored as structured JSON.
- Report versions, status history, assignment history, and moderation status fields.
- RBAC roles: citizen, lga_officer, agency_officer, triage_officer, supervisor, state_admin, auditor, moderator.
- Government queue, assignment, status update, internal notes, and analytics API.
- State-admin-only government account provisioning endpoint (`POST /government/users`).
- Moderator/state-admin visibility controls for reports and comments.
- One government portal / API with multiple permission-controlled queues; no separate API endpoint per agency is required.
- LGA and agency routing is a configurable human-confirmed workflow. It does not claim to know real road ownership until the agency directory/rules are configured with government.

## Important production gaps to close
1. Replace demo seeding and local uploads; use private object storage, malware scanning, image metadata stripping, signed download URLs, and retention rules.
2. Add email verification, password reset, MFA for privileged users, session revocation, account lockout, rate limits, CSRF strategy where cookies are used, and stronger abuse prevention.
3. Add migrations (Alembic), formal audit-log immutability, monitoring, backups, restore drills, secret management, CI tests, and deployment infrastructure.
4. Confirm actual Anambra agency responsibilities, LGA receiving desks, road ownership data, service targets, escalation agreements, and federal referral procedures.
5. Establish moderation policy and staffing; protect personal data; publish privacy notice, terms, retention schedule, and appeals process.
6. Conduct independent security, privacy, accessibility, and performance reviews before handling real public reports.

## Report lifecycle
`submitted -> under_review -> verified -> assigned -> in_progress -> awaiting_information -> resolved -> closed`; reports can also be `rejected` or `reopened`. Only authorized government roles can change status. Significant content edits create a version entry. The public sees only public notes/responses; internal notes are restricted.

## Roles and scope
- Citizen: public feed, own reports, support, comments.
- LGA officer: reports within assigned LGA; may refer/assign only within configured permissions.
- Agency officer: cases assigned to their agency.
- Triage officer/supervisor/state admin: cross-queue functions within role permissions.
- Auditor: read-only case/audit review (audit UI is intentionally basic in this foundation).
- Moderator: hide/restore public content according to moderation rules.

The first admin seed account has state-level privileges. Production administrators should be provisioned securely, not through public registration. A state admin can provision authorized staff through `POST /government/users`; restrict this operation to designated administrators and use secure out-of-band password delivery.
>>>>>>> 5389391 (3mtt x RAIN x Meta Capstone demo)
