# 🔵 AURA — AI Web Extractor

> Point AURA at any URL. Get a clean spreadsheet in seconds.

Built with **Streamlit** + **Claude (Anthropic)** · Deployable on **Streamlit Community Cloud** for free.

---

## 🗂️ Repository Structure

```
aura-scraper/
├── .streamlit/
│   ├── config.toml            ← Theme & server settings
│   └── secrets.toml.example  ← Secret template (do not commit real secrets)
├── app.py                     ← Main Streamlit application
├── requirements.txt           ← Python dependencies
├── .gitignore                 ← Excludes secrets & caches
└── README.md
```

---

## 🚀 Deploy to Streamlit Community Cloud (Free)

### Step 1 — Push to GitHub
```bash
git init
git add .
git commit -m "Initial AURA commit"
gh repo create aura-scraper --public --push
```

### Step 2 — Create Streamlit Account
Go to [share.streamlit.io](https://share.streamlit.io) → Sign up with GitHub.

### Step 3 — Deploy
1. Click **"Create app"** → **"I have an app"**
2. Select your repo: `your-username/aura-scraper`
3. Branch: `main`
4. Main file: `app.py`
5. (Optional) Set a custom subdomain e.g. `aura-extractor`
6. Click **"Advanced settings"** → paste your secrets (see below)
7. Click **"Deploy"** 🎉

### Step 4 — Add Secrets
In the Advanced settings or App Settings → Secrets tab, paste:

```toml
ANTHROPIC_API_KEY = "sk-ant-your-key-here"
```

> ⚠️ Never commit `secrets.toml` to GitHub. Always use the Streamlit Cloud secrets dashboard.

---

## 🔧 Run Locally

```bash
pip install -r requirements.txt

# Create real secrets file (not committed)
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml and add your real key

streamlit run app.py
```

---

## ✨ Features

| Feature | Status |
|--------|--------|
| 🧠 AI Column Naming (Claude) | ✅ |
| 📊 HTML Table Detection | ✅ |
| 🃏 Card / List Pattern Detection | ✅ |
| 🤖 robots.txt Checker | ✅ |
| 🚦 Rate Limiting | ✅ |
| 🔒 PII Warning | ✅ |
| ✂️ Trim Whitespace | ✅ |
| 🗑️ De-duplication | ✅ |
| ✏️ Column Rename & Reorder | ✅ |
| ⬇️ CSV / JSON / Excel Export | ✅ |

---

## ⚖️ Ethical Scraping

AURA is designed to respect the web:
- Checks `robots.txt` before every scrape
- Enforces configurable request delays
- Warns when PII columns are detected
- Uses a transparent User-Agent string

---

## 🧰 Tech Stack

- **Frontend / App:** Streamlit
- **AI:** Anthropic Claude (claude-sonnet-4)
- **Scraping:** Requests + BeautifulSoup4
- **Data:** Pandas
- **Excel:** OpenPyXL
- **Hosting:** Streamlit Community Cloud (free)
