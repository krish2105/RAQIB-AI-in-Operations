# RBAC route matrix (v2, Phase J)

Roles: **viewer < operator < manager < admin**. Every route maps to one capability; the capability names the minimum role. Site scoping: a user with `site_ids` set can only read or act on those sites; an empty list means every site. With `AUTH_REQUIRED=false` (local dev, the public demo) an unauthenticated request acts as the dev admin; with `AUTH_REQUIRED=true` every route needs a Supabase Auth JWT (magic link or Google), verified server-side with the project's JWT secret or JWKS.

| Capability | Minimum role | Routes |
|---|---|---|
| read | viewer | `GET /events*`, `/clips/{id}`, `/actions*`, `/toolcalls*`, `/kpis`, `/forecast`, `/workforce`, `/report/*`, `/sites*`, `/documents*`, `/twin/*`, `/shelves`, `/pos/summary|transactions|sample`, `/crew/status|roster|runs|messages|actions|memory*`, `/vlm/opinions|summary`, `/captions`, `/detections/latest`, `/cameras/*`, `/policy`, `/auth/me`, `/integrations/status`, `/notify/optins` |
| ask | viewer, rate limited per user (`RATE_ASK_PER_MIN`, default 20) | `POST /ask`, `GET /ask/stream`, `GET /ask/history` |
| approve | operator | `POST /actions/{id}/approve|reject`, `POST /vlm/opinion/{id}` (also rate limited, `RATE_VLM_PER_MIN`), `POST/DELETE /notify/optins` |
| ingest | operator (the edge box's service account) | `POST /events/batch`, `PUT /clips/{id}`, `POST /detections` |
| manage | manager | `POST /admin/seed|index|reset`, `POST /documents`, `POST /pos/import`, `POST /crew/memory`, `POST /crew/memory/snapshot` |
| policy | admin | `PUT /policy`, `POST /crew/kill|resume`, `POST /crew/memory/rollback`, `GET /auth/users`, `PATCH /auth/users/{id}` |

Bootstrapping: emails in `AUTH_ADMIN_EMAILS` become admin on first login; everyone else gets `AUTH_DEFAULT_ROLE` (viewer). Roles and site ids are edited by an admin through `PATCH /auth/users/{id}`; tokens never carry roles, the `users` table does.
