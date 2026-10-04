@echo off
cd /d %~dp0
if not exist .venv python -m venv .venv
call .venv\Scripts\activate
pip install -r backend\requirements.txt
uvicorn backend.main:app --reload
