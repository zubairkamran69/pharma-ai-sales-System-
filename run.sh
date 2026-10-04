#!/usr/bin/env bash
cd "$(dirname "$0")"
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate
pip install -r backend/requirements.txt
uvicorn backend.main:app --reload
