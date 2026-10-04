# Production Deployment

## Architecture

```text
Vercel static frontend -> Vercel /api rewrite -> Render FastAPI -> Neon PostgreSQL
```

The frontend is plain static HTML/JavaScript, not a Vite build. It calls relative `/api` URLs; `frontend/vercel.json` proxies those requests to the Render service. Do not configure `VITE_API_URL` unless the frontend is migrated to Vite.

## Neon

1. Create a Neon PostgreSQL project and database.
2. Copy its pooled or direct connection URL and keep it private.
3. Ensure the URL includes `sslmode=require` (the backend also enforces SSL).
4. Never commit the URL or put it in Vercel variables.

The backend creates missing tables and applies additive `ALTER TABLE` migrations at startup. It does not drop tables, reset records, or seed default production data. Uploaded files are stored in the `documents.file_data` BYTEA column; readable files from the legacy Render disk are copied into this column during startup without clearing their old paths.

## Render

Create/update the Web Service from the repository Blueprint (`render.yaml`). The service root is the repository root.

- Build command: `pip install -r backend/requirements.txt`
- Start command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Python: `.python-version` pins `3.12.8`; `runtime.txt` is retained as an additional selector.
- Health check: `/api/health`

Set these Render environment variables:

| Variable | Required | Notes |
| --- | --- | --- |
| `DATABASE_URL` | Yes | Neon PostgreSQL URL; keep private. |
| `JWT_SECRET` | Yes | Use a unique random value of at least 32 characters. The Blueprint can generate one. |
| `CLIENT_URL` | Yes | Exact production Vercel origin, e.g. `https://your-project.vercel.app`; no trailing slash. |
| `ADMIN_EMAIL` | Optional | Initial platform admin email. Set together with `ADMIN_PASSWORD`. |
| `ADMIN_PASSWORD` | Optional | Initial admin password; account is created only if its email is absent. |
| `DEMO_USER_EMAIL` | Optional | Initial demo doctor email. Set together with `DEMO_USER_PASSWORD`. |
| `DEMO_USER_PASSWORD` | Optional | Demo user password; account is created only if absent. |
| `GROQ_API_KEY` | If using Groq | Keep private. Set `LLM_PROVIDER=groq`. |
| `LLM_PROVIDER` | Optional | `groq` for hosted inference, or `demo` for extractive demo responses. |
| `LLM_API_KEY` | Optional | Generic hosted provider key; `GROQ_API_KEY` is also supported. |
| `LLM_BASE_URL` | Optional | OpenAI-compatible endpoint override. |
| `LLM_MODEL` | Optional | Hosted model override. |
| `GROQ_MODEL` | Optional | Defaults to `openai/gpt-oss-20b`. |
| `OPENAI_API_KEY`, `OPENAI_MODEL`, `OPENAI_BASE_URL` | Optional | OpenAI-compatible provider settings. |
| `OLLAMA_BASE_URL`, `OLLAMA_MODEL` | Optional | Use only if Ollama is reachable from the backend host. |
| `CORS_ORIGINS` | Optional | Comma-separated additional exact origins; `CLIENT_URL` is included automatically. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | Optional | Defaults to `720`. |
| `DEMO_VERIFICATION` | Optional | Keep `false` in production. |
| `UPLOAD_DIR` | Legacy only | Retained by the Blueprint disk for migration of older file paths; new uploads are stored in Neon. |

Restart/redeploy after changing environment values. Do not paste secrets into GitHub or chat. Rotate any Neon URL previously exposed in a repository file or conversation.

## Vercel

1. Import this repository.
2. Set the project root directory to `frontend` and use no build command (static site).
3. Confirm `frontend/vercel.json` points `/api/*` to the actual Render service URL. Update its destination if the Render service hostname changes.
4. Set `CLIENT_URL` in Render to the exact Vercel production origin. Add preview origins to `CORS_ORIGINS` only when needed.

No Vercel API secret or Neon variable is needed; the browser talks to Vercel's same-origin `/api` rewrite.

## Safe deployment sequence

1. Rotate any exposed database credentials; set `DATABASE_URL` and a new `JWT_SECRET` in Render.
2. Set `CLIENT_URL`, and optionally the paired admin/demo credentials and Groq key.
3. Deploy the Render Blueprint and verify `/api/health` returns `healthy`.
4. Deploy the static frontend to Vercel and test login, company-scoped data, messages, orders, and document upload.
5. Confirm the uploaded file has a database row and a non-null `file_data` value before removing any legacy persistent disk.

Never remove the existing Render disk until legacy file migration is verified. Schema changes are additive and preserve existing records; back up the Neon project before production rollout.
