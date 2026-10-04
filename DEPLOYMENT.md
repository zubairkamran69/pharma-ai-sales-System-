# Production Deployment

## Architecture

```text
Vercel Vite frontend -> Render FastAPI -> Neon PostgreSQL
```

The UI remains the existing HTML/CSS/JavaScript, built by Vite so Vercel can inject `VITE_API_URL`. API requests go directly to Render; Vercel does not proxy or serve backend routes.

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
| `CLIENT_URL` | Yes | Exact production Vercel origin, currently `https://pharma-ai-sales-system-frontend.vercel.app`; no trailing slash. |
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

1. Import this repository and set the project root directory to `frontend`.
2. Use `npm run build` as the build command and `dist` as the output directory.
3. Set the Vercel environment variable `VITE_API_URL` to `https://pharma-ai-sales-system.onrender.com` (the active Render API URL used by the production frontend), for Production and any environments you deploy. If the Render service URL changes, update this value to the URL shown for that service.
4. Set `CLIENT_URL` in Render to the exact Vercel production origin shown above. Add preview origins to `CORS_ORIGINS` only when needed.

No database or API secret belongs in Vercel. The browser calls `${VITE_API_URL}/api/...` directly.

## Safe deployment sequence

1. Rotate any exposed database credentials; set `DATABASE_URL` and a new `JWT_SECRET` in Render.
2. Set `CLIENT_URL`, and optionally the paired admin/demo credentials and Groq key.
3. Deploy the Render Blueprint and verify `/api/health` returns `healthy`.
4. Deploy the existing frontend through Vite to Vercel and test login, company-scoped data, messages, orders, and document upload. Confirm browser requests use the Render origin, not the Vercel origin.
5. Confirm the uploaded file has a database row and a non-null `file_data` value before removing any legacy persistent disk.

Never remove the existing Render disk until legacy file migration is verified. Schema changes are additive and preserve existing records; back up the Neon project before production rollout.
