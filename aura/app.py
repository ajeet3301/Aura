import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import json
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
from anthropic import Anthropic

# ── Page config ──────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AURA — AI Web Extractor",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Inject AURA CSS ───────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&family=Inter:wght@300;400;500&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0b0f19;
    color: #e6ecff;
}

/* Hide default Streamlit branding */
#MainMenu, footer, header { visibility: hidden; }

.block-container { padding-top: 2rem; max-width: 1200px; }

/* Headings */
h1, h2, h3 { font-family: 'Poppins', sans-serif !important; }

/* Hero */
.aura-hero {
    text-align: center;
    padding: 3rem 1rem 2rem;
}

.aura-logo {
    font-family: 'Poppins', sans-serif;
    font-size: 3rem;
    font-weight: 800;
    background: linear-gradient(135deg, #7c9cff, #00e0ff);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: 6px;
    margin-bottom: 0.5rem;
}

.aura-tagline {
    color: #9aa4c7;
    font-size: 1rem;
    margin-bottom: 0.25rem;
}

/* Cards */
.glass-card {
    background: rgba(18,24,38,0.7);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    padding: 1.5rem;
    margin-bottom: 1rem;
    backdrop-filter: blur(12px);
}

/* Status badges */
.badge-ok   { display:inline-block;padding:3px 12px;background:rgba(40,200,64,0.12);border:1px solid rgba(40,200,64,0.3);border-radius:20px;color:#28c840;font-size:.78rem;font-weight:500; }
.badge-warn { display:inline-block;padding:3px 12px;background:rgba(254,188,46,0.12);border:1px solid rgba(254,188,46,0.3);border-radius:20px;color:#febc2e;font-size:.78rem;font-weight:500; }
.badge-err  { display:inline-block;padding:3px 12px;background:rgba(255,95,87,0.12);border:1px solid rgba(255,95,87,0.3);border-radius:20px;color:#ff5f57;font-size:.78rem;font-weight:500; }
.badge-ai   { display:inline-block;padding:3px 12px;background:rgba(124,156,255,0.12);border:1px solid rgba(124,156,255,0.3);border-radius:20px;color:#7c9cff;font-size:.78rem;font-weight:500; }

/* Divider */
.aura-divider {
    border: none;
    border-top: 1px solid rgba(255,255,255,0.06);
    margin: 1.5rem 0;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: #121826;
    border-right: 1px solid rgba(255,255,255,0.06);
}
</style>
""", unsafe_allow_html=True)

# ── Helpers ───────────────────────────────────────────────────────────────────
def check_robots_txt(url: str) -> tuple[bool, str]:
    """Returns (allowed, message)."""
    try:
        parsed = urlparse(url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        allowed = rp.can_fetch("*", url)
        return allowed, robots_url
    except Exception:
        return True, "Could not read robots.txt — proceeding with caution."


def rate_limited_get(url: str, delay: float = 1.5) -> requests.Response:
    time.sleep(delay)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (compatible; AURA-Bot/1.0; +https://aura-scraper.streamlit.app)"
        )
    }
    return requests.get(url, headers=headers, timeout=15)


def extract_tables(soup: BeautifulSoup) -> list[pd.DataFrame]:
    """Extract all HTML <table> elements into DataFrames."""
    dfs = []
    for table in soup.find_all("table"):
        try:
            df = pd.read_html(str(table))[0]
            if not df.empty:
                dfs.append(df)
        except Exception:
            pass
    return dfs


def extract_list_items(soup: BeautifulSoup) -> list[dict]:
    """Detect repeating card/list patterns and return rows."""
    rows = []
    candidates = soup.select("li, article, [class*='card'], [class*='item'], [class*='product'], [class*='result']")
    for el in candidates[:200]:
        text = el.get_text(separator=" | ", strip=True)
        if len(text) > 20:
            links = [a.get("href", "") for a in el.find_all("a", href=True)]
            rows.append({"text": text, "links": ", ".join(links[:3])})
    return rows


def detect_pii(df: pd.DataFrame) -> list[str]:
    """Warn about potential PII columns."""
    pii_keywords = ["email", "phone", "address", "ssn", "passport", "dob", "birth", "national", "tax"]
    found = []
    for col in df.columns:
        if any(k in str(col).lower() for k in pii_keywords):
            found.append(str(col))
    return found


def ai_map_columns(html_snippet: str, client: Anthropic) -> dict:
    """Ask Claude to suggest better column names from raw HTML."""
    prompt = f"""
You are a web scraping assistant. Given this HTML snippet, identify what data fields are present 
and suggest clean, human-friendly column header names. Return ONLY a JSON object like:
{{"original_key": "Suggested Name", ...}}

HTML:
{html_snippet[:3000]}
"""
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}],
    )
    text = response.content[0].text.strip()
    try:
        text = re.sub(r"```json|```", "", text).strip()
        return json.loads(text)
    except Exception:
        return {}


def clean_df(df: pd.DataFrame, trim: bool, dedup_col: str | None) -> pd.DataFrame:
    if trim:
        df = df.apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))
    if dedup_col and dedup_col in df.columns:
        df = df.drop_duplicates(subset=[dedup_col])
    return df.reset_index(drop=True)


# ── Session state ─────────────────────────────────────────────────────────────
if "scraped_df" not in st.session_state:
    st.session_state.scraped_df = None
if "raw_html" not in st.session_state:
    st.session_state.raw_html = ""
if "robots_ok" not in st.session_state:
    st.session_state.robots_ok = True
if "log" not in st.session_state:
    st.session_state.log = []

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="aura-logo" style="font-size:1.6rem;letter-spacing:4px;">AURA</div>', unsafe_allow_html=True)
    st.caption("AI Web Extractor · v1.0")
    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

    st.subheader("⚙️ Extraction Settings")
    mode = st.radio("Data Source", ["Auto-detect", "Tables only", "List/Cards only"], index=0)
    use_ai_naming = st.toggle("🧠 AI Column Naming", value=True)
    trim_ws = st.toggle("✂️ Trim Whitespace", value=True)
    dedup = st.toggle("🗑️ Remove Duplicates", value=False)
    dedup_col = None

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

    st.subheader("🔒 Safety")
    check_robots = st.toggle("Check robots.txt", value=True)
    rate_limit_delay = st.slider("Request delay (seconds)", 0.5, 5.0, 1.5, 0.5)

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)
    st.caption("Built with ❤️ · Respects robots.txt · Rate limited · PII detection")

# ── Hero ──────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="aura-hero">
    <div class="aura-logo">AURA</div>
    <div style="font-family:Poppins,sans-serif;font-size:1.4rem;font-weight:600;margin-bottom:.5rem;">
        AI-Powered Web Extractor
    </div>
    <div class="aura-tagline">Point AURA at any URL. Get a clean spreadsheet in seconds.</div>
</div>
""", unsafe_allow_html=True)

# ── URL Input ─────────────────────────────────────────────────────────────────
col_url, col_btn = st.columns([5, 1])
with col_url:
    url_input = st.text_input(
        "Website URL",
        placeholder="https://example.com/products",
        label_visibility="collapsed",
    )
with col_btn:
    extract_btn = st.button("⚡ Extract", use_container_width=True, type="primary")

st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

# ── Extraction Logic ──────────────────────────────────────────────────────────
if extract_btn and url_input:
    st.session_state.log = []
    st.session_state.scraped_df = None

    with st.status("🔵 AURA is working...", expanded=True) as status:

        # 1. Robots check
        if check_robots:
            st.write("🤖 Checking robots.txt...")
            allowed, robots_url = check_robots_txt(url_input)
            st.session_state.robots_ok = allowed
            if not allowed:
                st.error(f"🚫 This site's robots.txt disallows scraping: {robots_url}")
                status.update(label="❌ Blocked by robots.txt", state="error")
                st.stop()
            else:
                st.write(f"✅ robots.txt OK — proceeding")

        # 2. Fetch page
        st.write(f"🌐 Fetching {url_input}...")
        try:
            resp = rate_limited_get(url_input, delay=rate_limit_delay)
            resp.raise_for_status()
        except Exception as e:
            st.error(f"Failed to fetch page: {e}")
            status.update(label="❌ Fetch failed", state="error")
            st.stop()

        soup = BeautifulSoup(resp.text, "html.parser")
        st.session_state.raw_html = resp.text[:5000]
        st.write(f"✅ Page fetched — {len(resp.text):,} characters")

        # 3. Extract data
        final_df = None

        if mode in ("Auto-detect", "Tables only"):
            st.write("📊 Scanning for HTML tables...")
            tables = extract_tables(soup)
            if tables:
                final_df = tables[0]  # take the largest/first
                for t in tables[1:]:
                    if len(t) > len(final_df):
                        final_df = t
                st.write(f"✅ Found {len(tables)} table(s) — using largest ({len(final_df)} rows)")

        if (final_df is None or final_df.empty) and mode in ("Auto-detect", "List/Cards only"):
            st.write("🃏 Scanning for repeating card/list patterns...")
            items = extract_list_items(soup)
            if items:
                final_df = pd.DataFrame(items)
                st.write(f"✅ Found {len(final_df)} list items")

        if final_df is None or final_df.empty:
            st.warning("⚠️ No structured data found. Try a different mode or URL.")
            status.update(label="⚠️ No data found", state="error")
            st.stop()

        # 4. AI column naming
        if use_ai_naming:
            st.write("🧠 AI is mapping column names...")
            try:
                client = Anthropic()
                mapping = ai_map_columns(resp.text, client)
                if mapping:
                    final_df = final_df.rename(columns=mapping)
                    st.write(f"✅ AI renamed {len(mapping)} column(s)")
                else:
                    st.write("ℹ️ AI found no renames needed")
            except Exception as e:
                st.write(f"⚠️ AI naming skipped: {e}")

        # 5. Clean
        st.write("🧹 Cleaning data...")
        final_df = clean_df(final_df, trim=trim_ws, dedup_col=None)

        # 6. PII check
        pii_cols = detect_pii(final_df)
        if pii_cols:
            st.warning(f"🔒 **PII Warning:** Possible personal data detected in columns: `{', '.join(pii_cols)}`")

        st.session_state.scraped_df = final_df
        status.update(label=f"✅ Extracted {len(final_df)} rows · {len(final_df.columns)} columns", state="complete")

# ── Results ───────────────────────────────────────────────────────────────────
if st.session_state.scraped_df is not None:
    df = st.session_state.scraped_df

    st.markdown("### 📋 Live Preview")

    # Column editor
    with st.expander("✏️ Rename / Reorder Columns", expanded=False):
        cols = list(df.columns)
        new_names = {}
        order_cols = st.multiselect("Column order", cols, default=cols)
        for col in order_cols:
            new_name = st.text_input(f"`{col}` →", value=str(col), key=f"rename_{col}")
            new_names[col] = new_name
        if st.button("Apply Changes"):
            df = df[order_cols].rename(columns=new_names)
            st.session_state.scraped_df = df
            st.rerun()

    # De-dup option
    if dedup:
        dedup_col = st.selectbox("De-duplicate by column", options=[""] + list(df.columns))
        if dedup_col:
            df = clean_df(df, trim_ws, dedup_col)
            st.session_state.scraped_df = df

    # Metrics
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Rows", f"{len(df):,}")
    m2.metric("Columns", f"{len(df.columns)}")
    m3.metric("Non-null cells", f"{df.count().sum():,}")
    m4.metric("Estimated size", f"{df.memory_usage(deep=True).sum() / 1024:.1f} KB")

    # Table
    st.dataframe(df, use_container_width=True, height=400)

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)
    st.markdown("### 📥 Export")

    dl1, dl2, dl3 = st.columns(3)

    # CSV
    csv_data = df.to_csv(index=False).encode("utf-8")
    dl1.download_button("⬇️ Download CSV", csv_data, "aura_extract.csv", "text/csv", use_container_width=True)

    # JSON
    json_data = df.to_json(orient="records", indent=2).encode("utf-8")
    dl2.download_button("⬇️ Download JSON", json_data, "aura_extract.json", "application/json", use_container_width=True)

    # Excel
    try:
        import io
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
        from openpyxl.utils import get_column_letter

        buf = io.BytesIO()
        wb = Workbook()
        ws = wb.active
        ws.title = "AURA Extract"

        header_fill = PatternFill("solid", fgColor="1C2640")
        header_font = Font(bold=True, color="7C9CFF", name="Calibri")

        for ci, col in enumerate(df.columns, 1):
            cell = ws.cell(row=1, column=ci, value=str(col))
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center")

        for ri, row in enumerate(df.itertuples(index=False), 2):
            for ci, val in enumerate(row, 1):
                ws.cell(row=ri, column=ci, value=val)

        for ci in range(1, len(df.columns) + 1):
            ws.column_dimensions[get_column_letter(ci)].width = 22

        wb.save(buf)
        buf.seek(0)
        dl3.download_button("⬇️ Download Excel", buf.read(), "aura_extract.xlsx",
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            use_container_width=True)
    except Exception as e:
        dl3.caption(f"Excel export unavailable: {e}")

# ── Empty State ───────────────────────────────────────────────────────────────
elif not extract_btn:
    st.markdown("""
<div class="glass-card" style="text-align:center;padding:3rem;">
    <div style="font-size:3rem;margin-bottom:1rem;">🔵</div>
    <div style="font-family:Poppins,sans-serif;font-size:1.2rem;font-weight:600;margin-bottom:.5rem;">
        Ready to extract
    </div>
    <div style="color:#9aa4c7;font-size:.9rem;">
        Paste a URL above and click Extract. AURA will detect tables, cards, and lists automatically.
    </div>
</div>
""", unsafe_allow_html=True)

    # Feature tiles
    f1, f2, f3 = st.columns(3)
    with f1:
        st.markdown("""<div class="glass-card">
            <b>🧠 AI Field Mapping</b><br>
            <span style="color:#9aa4c7;font-size:.85rem;">Claude reads the page and names your columns intelligently.</span>
        </div>""", unsafe_allow_html=True)
    with f2:
        st.markdown("""<div class="glass-card">
            <b>📊 Table + Card Detection</b><br>
            <span style="color:#9aa4c7;font-size:.85rem;">Finds HTML tables and repeating card patterns automatically.</span>
        </div>""", unsafe_allow_html=True)
    with f3:
        st.markdown("""<div class="glass-card">
            <b>🔒 Ethical Scraping</b><br>
            <span style="color:#9aa4c7;font-size:.85rem;">robots.txt checked · rate limited · PII warning built-in.</span>
        </div>""", unsafe_allow_html=True)
