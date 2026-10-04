# PharmaAI Sales Agent

PharmaAI is a role-based pharmaceutical engagement demo with workspaces for doctors, pharma companies, sales representatives, and platform administrators. It combines product discovery, orders, private human sales conversations, document retrieval, and configurable AI assistance in one FastAPI application with a static web frontend.

> **Demo and safety notice:** Medicine and account records may be synthetic. Product content is not clinical guidance, and the platform does not provide government credential verification unless connected to an authorized registry.

## Core architecture

```text
Doctor / Pharma / Sales Rep / Owner
                ↓
        Supervisor Agent
                ↓
 ┌──────────────┼───────────────────┐
 ↓              ↓                   ↓
RAG Agent   Intelligence Tools   Safety Agent
 ↓              ↓                   ↓
Approved KB  Doctors/Products   Human Escalation
                ↓
        Human Sales Handoff
                ↓
 Doctor ↔ Real Sales Representative
```

## Roles

### Doctor
- Public self-registration with medical specialization + license/registration number.
- Profile and professional credentials.
- Verification status.
- Global approved product/medicine RAG across participating companies.
- Specialty-to-product matching.
- Product requests/orders.
- AI conversational assistant.
- One-click **Talk to representative** handoff.
- Human chat with a real sales representative.

### Pharma Company
- Public self-registration with company registration/license number.
- Company-scoped medicines.
- Company-wide and medicine-specific RAG document uploads.
- AI company agent.
- All verified registered doctors directory.
- Specialty/product matching recommendations.
- Sales representative management.
- Doctor ↔ representative conversation history.
- Orders, escalations and analytics.

### Sales Representative
Sales representatives are **not publicly registered**. A verified pharma company creates them from **Sales Representatives**.

Each representative gets:
- Name
- Email
- Password
- Phone
- Job title
- Unique Sales ID
- Company relationship
- Human doctor chat access
- Company product/RAG access
- Doctor and order context

### Owner Admin
The platform owner is private and has a separate login. The admin panel can see:
- All doctors
- All pharma companies
- All sales representatives
- Verification status
- Credentials/registration numbers
- Platform RAG/document counts
- Escalation counts

The platform owner cannot list, open, or send messages in private doctor-to-company human sales conversations.

## Authentication and verification

Public account creation is intentionally limited to **Doctor** and **Pharma Company**.

A new account normally enters `pending` status. The owner admin can approve/reject it from **Verification & Users**.

For the Pakistan demo, doctor registration uses PM&DC-style license information. PM&DC currently provides a public practitioner register searchable by registration number, full name or father name, including license validity and registered qualifications: https://www.pmdc.pk/Home?keyWord=registration

The project does **not** pretend that it has an unauthorized government API. The demo includes a verification adapter/owner approval workflow. For production, connect an official regulator API or an explicitly authorized verification service. `DEMO_VERIFICATION=true` allows credentials beginning with `DEMO-` to pass automatically for hackathon testing.

## Demo accounts

```text
Pharma Company
owner@pharmaai.local
owner123

Doctor
doctor@pharmaai.local
doctor123

Sales Representative
sarah.rep@pharmaai.local
rep123

Private Owner Admin
admin@pharmaai.local
admin123
```

The supplied accounts are fictional demo identities.

## Conversational agent

The chat is designed to behave like a general conversational supervisor rather than a keyword-only FAQ bot.

Examples for a pharma company:

- `Hello`
- `What can you help me with?`
- `Help me upload a medicine document`
- `Show all new doctors`
- `Which doctors match Cardiovex 10?`
- `Show my sales representatives`
- `What is in my RAG knowledge base?`

Examples for a doctor:

- `Hello`
- `What medicines match my specialty?`
- `Tell me about Cardiovex 10`
- `What information came from the approved document?`
- `Connect me with the sales representative`

The supervisor routes requests to RAG, structured tools, doctor intelligence, sales tools, safety handling or human handoff.

## LLM modes

### 1. Demo — completely offline

```env
LLM_PROVIDER=demo
```

This mode uses an explicitly labeled extractive demo responder, not an LLM. It selects text from retrieved sources and must not be presented as model inference.

### 2. Free local LLM — Ollama

Install Ollama locally, download any supported local chat model, then configure:

```env
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434/api/chat
OLLAMA_MODEL=llama3.2:3b
```

This keeps inference local and avoids per-request API charges. The RAG and safety architecture stays the same.

### 3. OpenAI-compatible API

```env
LLM_PROVIDER=openai
LLM_API_KEY=your_key
LLM_MODEL=gpt-4o-mini
LLM_BASE_URL=https://api.openai.com/v1/chat/completions
```

Hosted provider errors are returned as errors; they do not silently switch to demo responses.

## Medicine RAG

```text
PDF / DOCX / TXT / MD
        ↓
Extraction
        ↓
Cleaning
        ↓
Chunking
        ↓
TF-IDF retrieval (offline demo)
        ↓
Relevant approved passages
        ↓
LLM synthesis
        ↓
Source citations
```

A company can upload:
- Product profiles
- Approved product information
- Safety documents
- Commercial/company documents
- Other authorized company knowledge

Company RAG is isolated by `owner_user_id`.

Doctor RAG can retrieve the approved product knowledge across participating companies.

## Human sales handoff

When a doctor views a medicine, the system can show **Talk to representative**.

The system:
1. Finds a verified representative for that medicine's company.
2. Creates/reuses a human conversation.
3. Notifies the representative.
4. Opens the conversation in the doctor portal.
5. Lets the doctor and representative message directly.
6. Keeps the complete conversation visible to the pharmaceutical company.
7. Stores the medicine/company context with the conversation.

A production version can add WebSocket live messaging, push notifications, presence, file sharing, call/meeting links and call-center integrations.

## Safety architecture

Safety runs before LLM generation.

Critical examples include patient-specific treatment, severe renal questions, pregnancy-related patient decisions, overdose, emergencies, adverse events and dosage changes.

The platform does not let the model autonomously make those decisions. It creates a human-review ticket and preserves the original conversation.

Commercial facts such as price, stock and orders come from structured backend tools, not model memory.

## Run on Windows

Neon PostgreSQL is required; the backend does not switch to a local database. Copy `.env.example` to `.env`, set `DATABASE_URL` to a newly generated Neon connection string, and set `JWT_SECRET` to a random value of at least 32 characters. Configure `CORS_ORIGINS` with the exact frontend origins used by the deployment.

Double-click:

```text
run.bat
```

Then open:

```text
http://127.0.0.1:8000
```

## Deploy: Render + Vercel

The repository includes `render.yaml` for the FastAPI service and `frontend/vercel.json` for the existing static frontend and same-origin API proxy.

1. In Render, create a Blueprint from this repository and select `render.yaml`. The service uses a persistent disk mounted at `/var/data` for uploaded documents.
2. In the Render service environment, set `DATABASE_URL` to a newly rotated Neon PostgreSQL URL. `JWT_SECRET` is generated by the Blueprint. Keep both values private.
3. Deploy the Render service. Its expected hostname is `https://pharmaai-sales-api.onrender.com`, as configured in the Vercel rewrite. If Render requires a different service name, update that destination before deploying the frontend.
4. In Vercel, import this repository and set the project root directory to `frontend`. No build step is needed; the output is the static frontend.
5. Open `https://<your-render-host>/api/health` and confirm the database/schema are healthy. Then test login and the main UI through the Vercel URL.

The Vercel rewrite keeps browser requests on the Vercel origin and proxies `/api/*` to Render. The frontend never receives the database URL. The database and JWT secret belong only in Render environment settings. Upload persistence depends on the Render plan supporting persistent disks.

## Manual run

```bash
python -m venv .venv
.venv\\Scripts\\activate
pip install -r backend\\requirements.txt
copy .env.example .env
uvicorn backend.main:app --reload
```

On startup, the backend validates the PostgreSQL connection and creates/upgrades its current application schema. `/api/health` reports database/schema status without returning credentials. This schema bootstrap is not yet a versioned migration system; back up Neon before schema changes.

## Main API groups

- `/api/auth/*` — authentication and public registration
- `/api/dashboard` — role dashboards
- `/api/profile` — professional profile
- `/api/medicines` — product catalog
- `/api/doctors` — verified doctor directory + matching
- `/api/reps` — company sales representative management
- `/api/chat` — supervisor/LLM/RAG/safety agent
- `/api/contact-rep/{medicine_id}` — human sales handoff
- `/api/human-conversations/*` — doctor ↔ sales rep messaging
- `/api/documents/{medicine_id}` — medicine RAG upload
- `/api/company-documents` — company RAG upload
- `/api/rag/*` — RAG status/search
- `/api/orders` — product requests/orders
- `/api/tickets` — human escalation
- `/api/admin/*` — private owner admin

## Synthetic demo data

`demo_data/Cardiovex_10_Demo_Approved_Product_Profile.pdf` is intentionally fictional. It is for demonstrating document ingestion, RAG, source citations, agent routing and safety escalation only. It must not be used for real clinical care, prescribing, promotion or regulatory decisions.

## Deployment and current limitations

The backend requires Neon-compatible PostgreSQL through `DATABASE_URL`; SQLite is not a runtime fallback. Documents and extracted chunks are stored in PostgreSQL metadata tables, while uploaded files remain on the backend filesystem and retrieval currently uses TF-IDF. pgvector embeddings, versioned migrations, a large repeatable 50-company/100-200-medicine seed set, and managed object storage are not implemented yet. Do not treat this repository as meeting those production-readiness criteria until those components and live Neon integration tests are completed.

Never commit `.env` or a real database URL/API key. A connection URL found in a repository environment template must be treated as compromised: revoke/rotate it in Neon and configure the replacement only in the deployment environment. Synthetic medicine content is not clinical guidance.
#   p h a r m a - a i - s a l e s - a g e n t 
 
 