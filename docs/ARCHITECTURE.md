# PharmaAI Full System Architecture

## Interfaces
1. Pharma Company Portal — sales command center, medicine catalog, doctor intelligence, agent console, orders, escalations, analytics.
2. Doctor Portal — personalized dashboard, medicine hub, AI medical/product assistant, requests, human support, profile.

## Agent flow
Doctor message → Supervisor Agent → intent/risk classification → Product Knowledge Agent (approved knowledge) OR Sales/Request Agent OR Follow-up Agent. Critical/uncertain/safety-sensitive requests → Risk Agent → Human Escalation → Medical Affairs/appropriate department.

## Persistence
The backend requires PostgreSQL through `DATABASE_URL` and fails closed if it is missing, the driver is unavailable, or the database cannot be reached. It does not fall back to SQLite. The current startup schema bootstrap maintains the existing application tables; it is not yet a versioned migration framework. RAG document metadata and chunks are stored in PostgreSQL, uploaded file bytes remain on backend disk, and retrieval currently uses TF-IDF rather than pgvector.

## Personalization
Every authenticated user is identified by user ID. Doctor dashboard queries use that ID, so Doctor A and Doctor B do not share sales, orders, earnings or conversations.
