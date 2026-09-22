# GitHub Email Scraper

Production-oriented GitHub profile scraper with a live Next.js dashboard and FastAPI backend.

## Pipeline

1. User chooses location, repository-count range, account-creation year range, and target count.
2. GitHub user search is sliced by account-creation year to avoid the search-result ceiling.
3. Users outside the repository range are skipped.
4. The public GitHub profile page is inspected for a visible email.
5. Only `@gmail.com` addresses continue. The optional quality gate rejects role-style addresses.
6. The user's earliest observable commit year is calculated across owned repositories by asking GitHub for the oldest matching commit on each default branch.
7. The rule is `account_creation_year - first_commit_year < 4`.
8. Previously collected Gmail addresses are skipped using the permanent `data/db.csv` history.
9. Accepted records are appended to `db.csv` and to a unique per-run CSV export.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# add your own GitHub token(s) to .env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Data

- `data/db.csv` is the append-only permanent history.
- Each scrape creates a unique CSV under `data/exports/MM-DD-YYYY/<location>/`.
- Never commit `backend/.env` or GitHub tokens.

## Tests

```bash
cd backend
pytest
```
