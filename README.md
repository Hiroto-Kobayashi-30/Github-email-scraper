# GitHub Email Scraper

Production-oriented GitHub profile email scraper with a Next.js dashboard and FastAPI backend.

## Important year behavior

The UI has **two year boxes** because they are the **account-creation search range**:

- `Account creation year from`
- `Account creation year to`

They can span multiple years (for example `2015` through `2026`). This is **not** sent as a multi-year GitHub contribution `from`/`to` window.

For the first-commit rule, GitHub's contribution API is queried in individual calendar-year windows. Each internal `from`/`to` window is safely less than one year, so GitHub's one-year limitation is not violated.

## Pipeline

1. Search GitHub users by location and account-creation year, one creation year at a time.
2. Read the user's public profile email directly from GraphQL; no HTML profile scraping.
3. Keep only Gmail addresses (with optional quality filtering).
4. Deduplicate the Gmail address **before** contribution-history queries.
5. Check commit contributions for the four calendar years beginning with the account creation year.
6. Accept when `account_creation_year - first_commit_year < 4`.
7. Append accepted records to `data/db.csv` and the current run CSV.

## Run locally

### Backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env
# put your own GitHub token(s) into backend/.env
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`.

## Token permissions

The GraphQL `User.email` field requires an appropriate token scope. For a classic PAT, grant `read:user` and/or `user:email`.

## Tests

```bash
cd backend
pytest
```
