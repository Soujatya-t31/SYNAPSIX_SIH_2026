#!/usr/bin/env bash
# Government Infrastructure Priority Engine — quick start
set -e
cd "$(dirname "$0")"

if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

source venv/bin/activate
pip install -q -r requirements.txt

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  echo "No .env found — password-reset emails will show on-screen instead of being sent."
  echo "(Copy .env.example to .env and fill in SMTP credentials to enable real emails.)"
fi

if [ ! -f "infra.db" ]; then
  echo "Initializing database and seeding demo data..."
  python3 seed_data.py
fi

echo ""
echo "Starting server at http://localhost:8000"
echo "  Landing page:          http://localhost:8000"
echo "  Citizen report form:   http://localhost:8000/citizen.html"
echo "  Sign in / Register:    http://localhost:8000/account.html"
echo "  My Reports (logged in):http://localhost:8000/profile.html"
echo "  Government dashboard:  http://localhost:8000/dashboard.html"
echo ""
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
