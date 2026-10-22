# CivicWatch — Architecture and Access Specification

## Product shape
CivicWatch has three connected experiences on one platform:
1. **Citizen platform:** social-style feed, authenticated accounts, issue reports, public comments, support, and My Reports.
2. **Government operations portal:** one authenticated portal with role- and scope-controlled queues, assignment, case status, internal notes, and audit history.
3. **Analytics:** authorized summaries by category, LGA, status, and severity.

The project is configured for Anambra as a case study, but categories, LGAs, agencies, and routing rules must become database-configurable before expansion to another state. The current LGA list and category list are configuration defaults, not a verified government routing directory.

## Report workflow
`submitted -> under_review -> verified -> assigned -> in_progress -> awaiting_information -> resolved -> closed`

Other available outcomes: `rejected`, `reopened`. This first code version records status history but does not yet enforce a complete formal transition graph. Define and test transition rules with participating agencies before production.

Citizen edits are permitted only for reports in `submitted`, `under_review`, or `reopened`. The old title, description, landmark, and details are snapshotted in `report_versions`. Once a report is assigned or later in the workflow, a correction-request feature should be added instead of allowing silent edits.

## Routing model
- The citizen selects the location and civic category; they do not have to know which authority owns the road or asset.
- A single central intake API accepts the report.
- LGA officers can see reports associated with their assigned LGA.
- Agency officers can see cases assigned to their agency identifier.
- Triage officers, supervisors, and state administrators can handle cross-queue work within their role.
- Assignment is human-confirmed. The current app does **not** contain verified Anambra road-ownership or agency-routing data. It must not automatically guess the responsible agency based only on category.
- External/federal referrals require an approved contact/process or integration; they are not automatic in this build.

## Role matrix (summary)

| Capability | Citizen | LGA officer | Agency officer | Triage / supervisor | State admin | Auditor | Moderator |
|---|---:|---:|---:|---:|---:|---:|---:|
| Browse public feed | Yes | Yes | Yes | Yes | Yes | Yes | Yes |
| Create citizen report | Yes | No | No | No | No | No | No |
| Support/comment | Yes | No special privilege | No special privilege | No special privilege | No special privilege | No special privilege | No special privilege |
| View own reports | Yes | — | — | — | — | — | — |
| Government queue | No | Own LGA | Assigned agency | Cross-queue | Cross-queue | Read-only permitted scope | No |
| Assign/reassign | No | Scoped referral | No | Yes | Yes | No | No |
| Update case status | No | Scoped LGA | Assigned agency | Yes | Yes | No | No |
| Internal notes | No | Scoped | Assigned agency | Yes | Yes | Not shown in case history response | No |
| Provision government accounts | No | No | No | No | Yes | No | No |
| Hide/restore public report/comment | No | No | No | No | Yes | No | Yes |
| View audit logs | No | No | No | No | Yes | Yes | No |

The backend is the authorization authority; hiding buttons in the frontend is not security. Review every endpoint and scope check before deployment. The table is a high-level design summary, not a substitute for endpoint-by-endpoint tests.

## Data model
- `users`: citizen and staff accounts; role and organizational scope.
- `reports`: structured civic report, location, category, severity, status, owner, assignment.
- `supports`: one support per account per report, enforced by a database unique constraint.
- `comments`: public issue-focused discussion; hidden comments remain in storage for traceability.
- `report_versions`: snapshot of editable report fields before corrections.
- `status_events`: status timeline and public/internal note flag.
- `assignment_events`: assignment history.
- `internal_notes`: government-only operational notes.
- `audit_logs`: recorded security and administrative actions.

## Main API routes
- `POST /auth/register`, `POST /auth/login`, `GET /auth/me`
- `GET /categories`, `GET /feed`, `GET /reports/{id}`, `GET /reports/mine`
- `POST /reports`, `PATCH /reports/{id}`, `POST /reports/{id}/upload`
- `POST /reports/{id}/support`, `POST /reports/{id}/comments`
- `GET /government/queue`, `POST /government/reports/{id}/assign`, `PATCH /government/reports/{id}/status`
- `POST /government/reports/{id}/internal-notes`, `GET /government/reports/{id}/history`
- `GET /government/analytics`, `POST /government/users`, `GET /government/audit-logs`
- `PATCH /government/reports/{id}/visibility`, `PATCH /government/comments/{id}/visibility`
- `GET /health`; interactive OpenAPI docs at `/docs`

## Security and privacy limitations to address before production
- JWT stored in browser localStorage in this demo; prefer secure HttpOnly cookies or an assessed token strategy, with refresh/revocation controls.
- No email verification, password reset, MFA, lockout, or invitation workflow yet.
- Local file uploads are served publicly by a development route. Replace with private object storage, content sniffing, malware scanning, EXIF stripping, access checks, and signed links.
- Audit logs are application-level records; they are not tamper-proof or immutable in this version.
- Comment moderation has manual hide/restore endpoints but no complete report/appeal queue or automated abuse protection.
- No rate limiting, bot protection, request-size controls at reverse proxy, secrets manager, CI/CD security scan, or formal migration framework.
- No formal jurisdiction directory, road ownership map, agency SLA, escalation agreements, or verified agency identifiers.
- No push/email/SMS delivery provider configured; frontend notices are local UI messages only.
- No production monitoring, backup/restore proof, load testing, accessibility audit, or independent security review.

## Analytics interpretation
The analytics API summarizes reports, statuses, severity, categories, and LGAs. Submission volume is not proof of incident frequency. Production analytics should add deduplication, distinct issue clusters, verification rate, response times, aging, reopened cases, reporting adoption context, and documented metric definitions.
