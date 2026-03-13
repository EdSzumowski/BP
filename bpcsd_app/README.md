# BPCSD Board Report Analysis

Internal tool for Broadalbin-Perth CSD Board of Education. Pulls Finance and Director reports
from BoardDocs and produces downloadable PDF trend analyses by school year or year-over-year.

## Authentication Model

This app uses **BoardDocs as the only authentication layer**. When a user opens the app,
they see a sign-in screen asking for their BoardDocs username and password. The app validates
those credentials directly against BoardDocs. If login fails, they cannot proceed.

No app-level passwords or Streamlit secrets are required.

## Deploy to Streamlit Community Cloud

### 1 — Push to a PRIVATE GitHub repo

```bash
git init
git add .
git commit -m "BPCSD analysis app"
git remote add origin https://github.com/YOUR_USERNAME/bpcsd-board-analysis.git
git push -u origin main
```

The .gitignore excludes venv/, cache/, and .streamlit/secrets.toml.
No credentials are committed to git.

### 2 — Connect to Streamlit Cloud

Go to share.streamlit.io → "New app" → select your repo → Main file: app.py → Deploy.

No secrets configuration needed. The app is ready to use immediately.

### 3 — Share the URL

Board members open the URL, enter their own BoardDocs credentials, and proceed.
Only users with valid BoardDocs accounts can access the analysis tools.

### 4 — Taking it down

Dashboard → ⋮ → Delete app. Immediately inaccessible. Redeploy any time.

## Running Locally

```bash
python3 -m venv venv
source venv/bin/activate       # macOS/Linux
pip install -r requirements.txt
streamlit run app.py
# Opens at http://localhost:8501
```

## Fiscal Year Note

School years run July 1 – June 30. July reorg meeting = year open. June = year close.
Meeting IDs are stored in modules/registry.py and extended as new meetings occur.
