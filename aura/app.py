import streamlit as st
import pandas as pd
import requests
from bs4 import BeautifulSoup
import re
import time
import json
import io
from urllib.robotparser import RobotFileParser
from urllib.parse import urljoin, urlparse
from anthropic import Anthropic

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AURA — AI Web Extractor",
    page_icon="🔵",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS ───────────────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Poppins:wght@300;400;600;700;800&family=Inter:wght@300;400;500&display=swap');

html, body, [class*="css"] { font-family:'Inter',sans-serif; background:#0b0f19; color:#e6ecff; }
#MainMenu, footer, header { visibility:hidden; }
.block-container { padding-top:1.5rem; max-width:1280px; }
h1,h2,h3 { font-family:'Poppins',sans-serif !important; }

.aura-logo {
    font-family:'Poppins',sans-serif; font-size:2.6rem; font-weight:800;
    background:linear-gradient(135deg,#7c9cff,#00e0ff);
    -webkit-background-clip:text; -webkit-text-fill-color:transparent;
    background-clip:text; letter-spacing:6px;
}
.aura-tagline { color:#9aa4c7; font-size:.95rem; }
.aura-divider { border:none; border-top:1px solid rgba(255,255,255,0.06); margin:1.2rem 0; }

.glass-card {
    background:rgba(18,24,38,0.75); border:1px solid rgba(255,255,255,0.08);
    border-radius:14px; padding:1.4rem; margin-bottom:.8rem;
}
.product-card {
    background:rgba(18,24,38,0.85); border:1px solid rgba(255,255,255,0.08);
    border-radius:16px; overflow:hidden; margin-bottom:1rem;
}
.product-body { padding:1rem; }
.product-title { font-family:'Poppins',sans-serif; font-weight:600; font-size:.92rem; margin-bottom:.4rem; color:#e6ecff; }
.product-price { color:#28c840; font-weight:700; font-size:1.05rem; margin-bottom:.3rem; }
.product-rating { color:#febc2e; font-size:.82rem; margin-bottom:.3rem; }
.product-desc { color:#9aa4c7; font-size:.78rem; line-height:1.5; margin-bottom:.4rem; }

.cat-pill {
    display:inline-block; padding:2px 9px;
    background:rgba(0,224,255,0.08); border:1px solid rgba(0,224,255,0.2);
    border-radius:20px; font-size:.7rem; color:#00e0ff; margin-right:4px; margin-bottom:4px;
}

.detail-table { width:100%; border-collapse:collapse; font-size:.85rem; }
.detail-table th { background:rgba(124,156,255,0.08); color:#7c9cff; padding:8px 12px; text-align:left; border-bottom:1px solid rgba(255,255,255,0.06); font-weight:500; }
.detail-table td { padding:8px 12px; border-bottom:1px solid rgba(255,255,255,0.04); color:#9aa4c7; vertical-align:top; }
.detail-table tr:hover td { background:rgba(124,156,255,0.04); color:#e6ecff; }
.detail-table td:first-child { font-weight:500; color:#e6ecff; width:28%; }

.stat-box { background:rgba(18,24,38,0.8); border:1px solid rgba(255,255,255,0.08); border-radius:12px; padding:1rem; text-align:center; }
.stat-num { font-family:'Poppins',sans-serif; font-size:1.8rem; font-weight:700; color:#7c9cff; }
.stat-label { font-size:.73rem; color:#9aa4c7; margin-top:2px; }

.cat-header { display:flex; align-items:center; gap:12px; padding:.7rem 1rem; background:rgba(18,24,38,0.6); border:1px solid rgba(255,255,255,0.07); border-radius:10px; margin-bottom:.8rem; }
.cat-count { font-size:.78rem; color:#9aa4c7; margin-left:auto; }

.img-thumb { width:100%; height:140px; object-fit:cover; border-radius:8px; border:1px solid rgba(255,255,255,0.06); display:block; }

section[data-testid="stSidebar"] { background:#121826; border-right:1px solid rgba(255,255,255,0.06); }
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def check_robots(url: str) -> bool:
    try:
        p = urlparse(url)
        rp = RobotFileParser()
        rp.set_url(f"{p.scheme}://{p.netloc}/robots.txt")
        rp.read()
        return rp.can_fetch("*", url)
    except Exception:
        return True


def fetch_page(url: str, delay: float = 1.5):
    time.sleep(delay)
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AURA-Bot/1.0)"}
    resp = requests.get(url, headers=headers, timeout=20)
    resp.raise_for_status()
    return resp


def resolve_img(src: str, base_url: str) -> str:
    if not src:
        return ""
    src = src.strip()
    if src.startswith("data:"):
        return ""
    if src.startswith("//"):
        return "https:" + src
    if src.startswith("http"):
        return src
    return urljoin(base_url, src)


def extract_images(soup: BeautifulSoup, base_url: str) -> list:
    seen = set()
    imgs = []
    for tag in soup.find_all("img"):
        src = (tag.get("src") or tag.get("data-src") or
               tag.get("data-lazy-src") or tag.get("data-original") or "")
        resolved = resolve_img(src, base_url)
        if resolved and resolved not in seen:
            ext = resolved.lower().split("?")[0]
            if any(ext.endswith(e) for e in [".jpg",".jpeg",".png",".webp",".gif",".svg"]):
                seen.add(resolved)
                alt = tag.get("alt","")
                width = tag.get("width","")
                height = tag.get("height","")
                imgs.append({"Image URL": resolved, "Alt Text": alt, "Width": width, "Height": height})
    return imgs


def extract_tables(soup: BeautifulSoup) -> list:
    dfs = []
    for t in soup.find_all("table"):
        try:
            df = pd.read_html(str(t))[0]
            if not df.empty:
                dfs.append(df)
        except Exception:
            pass
    return dfs


def extract_meta(soup: BeautifulSoup) -> dict:
    meta = {}
    meta["Page Title"] = soup.title.get_text(strip=True) if soup.title else ""
    for m in soup.find_all("meta"):
        name = m.get("name") or m.get("property") or ""
        content = m.get("content") or ""
        if name and content:
            meta[name] = content
    # canonical
    canonical = soup.find("link", rel="canonical")
    if canonical:
        meta["canonical"] = canonical.get("href","")
    return meta


def extract_links(soup: BeautifulSoup, base_url: str) -> list:
    seen = set()
    rows = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        text = a.get_text(strip=True)
        full = urljoin(base_url, href)
        if full not in seen and text:
            seen.add(full)
            try:
                domain = urlparse(full).netloc
            except Exception:
                domain = ""
            rows.append({"Link Text": text, "URL": full, "Domain": domain})
    return rows


def extract_headings(soup: BeautifulSoup) -> list:
    rows = []
    for tag in ["h1","h2","h3","h4","h5","h6"]:
        for el in soup.find_all(tag):
            text = el.get_text(strip=True)
            if text:
                rows.append({"Level": tag.upper(), "Text": text})
    return rows


def extract_structured_items(soup: BeautifulSoup, base_url: str) -> list:
    """Deep extraction of repeating items with all fields."""
    price_re  = re.compile(r'[\$£€₹¥]\s?\d[\d,\.]*|\d[\d,\.]*\s*(?:USD|EUR|GBP|INR)')
    rating_re = re.compile(r'(\d[\.,]\d)\s*(?:out of|\/\d|stars?|★)', re.I)

    selectors = [
        "article", "[class*='product']", "[class*='card']",
        "[class*='item']", "[class*='listing']", "[class*='result']",
        "[class*='post']", "[class*='news']", "[class*='job']", "li"
    ]

    candidates = []
    for sel in selectors:
        found = soup.select(sel)
        if len(found) >= 3:
            candidates = found[:150]
            break

    items = []
    for el in candidates:
        text = el.get_text(separator=" ", strip=True)
        if len(text) < 15:
            continue

        row = {}

        # Title
        for t in ["h1","h2","h3","h4","h5","a"]:
            tag = el.find(t)
            if tag:
                row["Title"] = tag.get_text(strip=True)[:220]
                break
        if "Title" not in row:
            row["Title"] = text[:120]

        # Image
        img_tag = el.find("img")
        if img_tag:
            src = (img_tag.get("src") or img_tag.get("data-src") or
                   img_tag.get("data-lazy-src") or img_tag.get("data-original") or "")
            row["Image URL"] = resolve_img(src, base_url)
            row["Image Alt"] = img_tag.get("alt","")
        else:
            row["Image URL"] = ""
            row["Image Alt"] = ""

        # Price
        pm = price_re.search(text)
        row["Price"] = pm.group(0).strip() if pm else ""

        # Rating
        rm = rating_re.search(text)
        row["Rating"] = rm.group(1).replace(",",".") if rm else ""

        # Link / URL
        link = el.find("a", href=True)
        row["URL"] = urljoin(base_url, link["href"]) if link else ""

        # Description — longest <p> inside
        paras = [p.get_text(strip=True) for p in el.find_all("p") if len(p.get_text(strip=True)) > 20]
        row["Description"] = paras[0][:350] if paras else ""

        # Category from data attrs
        cat = (el.get("data-category") or el.get("data-type") or
               el.get("data-section") or el.get("data-department") or "")
        row["Category"] = cat

        # Brand
        brand = el.get("data-brand") or el.get("data-seller") or ""
        row["Brand"] = brand

        # SKU / ID
        sku = el.get("data-sku") or el.get("data-id") or el.get("data-product-id") or ""
        row["SKU / ID"] = sku

        # Availability
        avail_re = re.compile(r'in stock|out of stock|available|unavailable|sold out', re.I)
        am = avail_re.search(text)
        row["Availability"] = am.group(0).title() if am else ""

        # Extra data-* attributes
        for attr, val in el.attrs.items():
            if (attr.startswith("data-") and val and
                    attr not in ["data-src","data-lazy-src","data-original",
                                 "data-category","data-type","data-brand",
                                 "data-sku","data-id","data-product-id"]):
                key = attr.replace("data-","").replace("-"," ").title()
                if len(str(val)) < 120:
                    row[key] = str(val)

        items.append(row)

    return items


def ai_analyze(html: str, client: Anthropic) -> dict:
    prompt = f"""Analyze this HTML page for web scraping. Return ONLY valid JSON (no markdown):
{{
  "page_type": "e-commerce|news|directory|blog|jobs|real-estate|other",
  "summary": "1-2 sentence description of what this page contains",
  "categories": ["list", "of", "detected", "categories or topics"],
  "column_map": {{"old_col": "Better Name"}},
  "key_fields": ["most important data fields found"]
}}

HTML (first 4000 chars):
{html[:4000]}"""

    resp = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=800,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = re.sub(r"```json|```", "", resp.content[0].text.strip()).strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"page_type":"other","summary":"","categories":[],"column_map":{},"key_fields":[]}


def detect_pii(df: pd.DataFrame) -> list:
    pii_kw = ["email","phone","mobile","address","ssn","passport","dob","birth","national","tax","aadhaar","pan"]
    return [c for c in df.columns if any(k in str(c).lower() for k in pii_kw)]


def clean_df(df: pd.DataFrame, trim: bool, dedup_col=None) -> pd.DataFrame:
    if trim:
        df = df.apply(lambda col: col.map(lambda x: x.strip() if isinstance(x, str) else x))
    if dedup_col and dedup_col in df.columns:
        df = df.drop_duplicates(subset=[dedup_col])
    return df.reset_index(drop=True)


def df_to_excel(df: pd.DataFrame) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter
    buf = io.BytesIO()
    wb = Workbook(); ws = wb.active; ws.title = "AURA Extract"
    hfill = PatternFill("solid", fgColor="1C2640")
    hfont = Font(bold=True, color="7C9CFF", name="Calibri")
    for ci, col in enumerate(df.columns, 1):
        c = ws.cell(row=1, column=ci, value=str(col))
        c.fill = hfill; c.font = hfont; c.alignment = Alignment(horizontal="center")
    for ri, row in enumerate(df.itertuples(index=False), 2):
        for ci, val in enumerate(row, 1):
            ws.cell(row=ri, column=ci, value=val)
    for ci in range(1, len(df.columns)+1):
        ws.column_dimensions[get_column_letter(ci)].width = 24
    wb.save(buf); buf.seek(0)
    return buf.read()

# ─────────────────────────────────────────────────────────────────────────────
# SESSION STATE
# ─────────────────────────────────────────────────────────────────────────────
defaults = {
    "items_df": None, "images": [], "links_df": None,
    "headings_df": None, "tables": [], "meta": {},
    "ai_info": {}, "raw_html": "", "base_url": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ─────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown('<div class="aura-logo">AURA</div>', unsafe_allow_html=True)
    st.caption("AI Web Extractor · v2.0")
    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

    st.subheader("⚙️ What to Extract")
    use_ai       = st.toggle("🧠 AI Page Analysis", value=True)
    extract_imgs = st.toggle("🖼️ Images", value=True)
    extract_lnks = st.toggle("🔗 Links", value=True)
    extract_hdrs = st.toggle("📝 Headings", value=True)
    extract_tbls = st.toggle("📊 HTML Tables", value=True)
    trim_ws      = st.toggle("✂️ Trim Whitespace", value=True)
    dedup        = st.toggle("🗑️ Remove Duplicates", value=False)

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)
    st.subheader("🔒 Safety")
    chk_robots      = st.toggle("Check robots.txt", value=True)
    rate_delay      = st.slider("Request delay (s)", 0.5, 5.0, 1.5, 0.5)
    max_img_preview = st.slider("Max image previews", 8, 60, 24, 4)

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)
    st.caption("Respects robots.txt · Rate limited · PII detection")

# ─────────────────────────────────────────────────────────────────────────────
# HERO
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="text-align:center;padding:2rem 1rem 1rem;">
  <div class="aura-logo">AURA</div>
  <div style="font-family:Poppins,sans-serif;font-size:1.2rem;font-weight:600;margin:.4rem 0 .3rem;">
    AI-Powered Web Extractor
  </div>
  <div class="aura-tagline">
    Images · Products · Cards · Tables · Links · Headings · Meta — every detail, every category.
  </div>
</div>
""", unsafe_allow_html=True)

col_url, col_btn = st.columns([5, 1])
with col_url:
    url_input = st.text_input("URL", placeholder="https://example.com/products or any page...",
                               label_visibility="collapsed")
with col_btn:
    extract_btn = st.button("⚡ Extract", use_container_width=True, type="primary")

st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
# EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────
if extract_btn and url_input:
    for k, v in defaults.items():
        st.session_state[k] = v

    with st.status("🔵 AURA is working...", expanded=True) as status:

        # 1 robots
        if chk_robots:
            st.write("🤖 Checking robots.txt...")
            if not check_robots(url_input):
                st.error("🚫 robots.txt disallows scraping this URL.")
                status.update(label="❌ Blocked by robots.txt", state="error")
                st.stop()
            st.write("✅ robots.txt — allowed")

        # 2 fetch
        st.write("🌐 Fetching page...")
        try:
            resp = fetch_page(url_input, delay=rate_delay)
        except Exception as e:
            st.error(f"Fetch failed: {e}")
            status.update(label="❌ Fetch failed", state="error")
            st.stop()

        soup = BeautifulSoup(resp.text, "html.parser")
        st.session_state.raw_html = resp.text
        st.session_state.base_url = url_input
        st.write(f"✅ Fetched — {len(resp.text):,} characters")

        # 3 AI
        if use_ai:
            st.write("🧠 AI analyzing page...")
            try:
                client = Anthropic()
                ai_info = ai_analyze(resp.text, client)
                st.session_state.ai_info = ai_info
                st.write(f"✅ Page type: **{ai_info.get('page_type','?')}** — {ai_info.get('summary','')[:100]}")
            except Exception as e:
                st.write(f"⚠️ AI skipped: {e}")

        # 4 items
        st.write("🃏 Extracting structured items...")
        items = extract_structured_items(soup, url_input)
        if items:
            df = pd.DataFrame(items)
            df = clean_df(df, trim_ws, None)
            col_map = st.session_state.ai_info.get("column_map", {})
            if col_map:
                df = df.rename(columns={k:v for k,v in col_map.items() if k in df.columns})
            if dedup:
                df = df.drop_duplicates(subset=["Title"]).reset_index(drop=True)
            pii = detect_pii(df)
            if pii:
                st.warning(f"🔒 PII detected in: `{', '.join(pii)}`")
            st.session_state.items_df = df
            st.write(f"✅ {len(df)} items · {len(df.columns)} fields each")
        else:
            st.write("ℹ️ No repeating items/cards detected")

        # 5 images
        if extract_imgs:
            st.write("🖼️ Collecting images...")
            imgs = extract_images(soup, url_input)
            st.session_state.images = imgs
            st.write(f"✅ {len(imgs)} images found")

        # 6 tables
        if extract_tbls:
            st.write("📊 Scanning HTML tables...")
            tables = extract_tables(soup)
            st.session_state.tables = tables
            st.write(f"✅ {len(tables)} table(s)")

        # 7 links
        if extract_lnks:
            st.write("🔗 Collecting links...")
            links = extract_links(soup, url_input)
            st.session_state.links_df = pd.DataFrame(links) if links else pd.DataFrame()
            st.write(f"✅ {len(links)} links")

        # 8 headings
        if extract_hdrs:
            st.write("📝 Extracting headings...")
            hdgs = extract_headings(soup)
            st.session_state.headings_df = pd.DataFrame(hdgs) if hdgs else pd.DataFrame()
            st.write(f"✅ {len(hdgs)} headings")

        # 9 meta
        st.write("🏷️ Reading page metadata...")
        st.session_state.meta = extract_meta(soup)

        status.update(label="✅ All categories extracted!", state="complete")

# ─────────────────────────────────────────────────────────────────────────────
# RESULTS
# ─────────────────────────────────────────────────────────────────────────────
has_data = any([
    st.session_state.items_df is not None,
    st.session_state.images,
    st.session_state.links_df is not None,
    st.session_state.tables,
])

if has_data:
    ai = st.session_state.ai_info

    # AI banner
    if ai:
        page_type = ai.get("page_type","")
        summary   = ai.get("summary","")
        cats      = ai.get("categories",[])
        key_flds  = ai.get("key_fields",[])
        icons     = {"e-commerce":"🛒","news":"📰","directory":"📋","blog":"✍️","jobs":"💼","real-estate":"🏠","other":"🌐"}
        icon      = icons.get(page_type,"🌐")
        cats_html = " ".join(f'<span class="cat-pill">{c}</span>' for c in cats[:12])
        flds_html = f'<div style="margin-top:.4rem;font-size:.77rem;color:#9aa4c7;">Key fields: {", ".join(key_flds[:8])}</div>' if key_flds else ""
        st.markdown(f"""
<div class="glass-card" style="border-left:3px solid #7c9cff;">
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
    <span style="font-size:1.8rem;">{icon}</span>
    <div>
      <div style="font-family:Poppins,sans-serif;font-weight:700;font-size:.95rem;">
        AI Detected: <span style="color:#7c9cff;">{page_type.replace('-',' ').title()}</span>
      </div>
      <div style="color:#9aa4c7;font-size:.82rem;">{summary}</div>
    </div>
  </div>
  <div style="margin-top:.7rem;">{cats_html}</div>
  {flds_html}
</div>""", unsafe_allow_html=True)

    # Stats
    items_df = st.session_state.items_df
    images   = st.session_state.images
    links_df = st.session_state.links_df
    tables   = st.session_state.tables
    hdgs_df  = st.session_state.headings_df
    meta     = st.session_state.meta

    c1,c2,c3,c4,c5 = st.columns(5)
    c1.markdown(f'<div class="stat-box"><div class="stat-num">{len(items_df) if items_df is not None else 0}</div><div class="stat-label">Items / Cards</div></div>', unsafe_allow_html=True)
    c2.markdown(f'<div class="stat-box"><div class="stat-num">{len(images)}</div><div class="stat-label">Images</div></div>', unsafe_allow_html=True)
    c3.markdown(f'<div class="stat-box"><div class="stat-num">{len(links_df) if links_df is not None else 0}</div><div class="stat-label">Links</div></div>', unsafe_allow_html=True)
    c4.markdown(f'<div class="stat-box"><div class="stat-num">{len(tables)}</div><div class="stat-label">Tables</div></div>', unsafe_allow_html=True)
    c5.markdown(f'<div class="stat-box"><div class="stat-num">{len(hdgs_df) if hdgs_df is not None else 0}</div><div class="stat-label">Headings</div></div>', unsafe_allow_html=True)

    st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

    # TABS
    tabs = st.tabs(["🃏 Items & Cards", "🖼️ Images", "📊 Tables", "🔗 Links", "📝 Headings", "🏷️ Page Meta", "📥 Export All"])

    # ── TAB 1: Items & Cards ─────────────────────────────────────────────────
    with tabs[0]:
        if items_df is not None and not items_df.empty:
            df = items_df.copy()

            view_mode = st.radio("View", ["🃏 Card Gallery", "📋 Table", "🔍 Detail Inspector"],
                                 horizontal=True, label_visibility="collapsed")

            col_s, col_f = st.columns([3,2])
            with col_s:
                search = st.text_input("Search", placeholder="Filter by keyword...", label_visibility="collapsed")
            with col_f:
                if "Category" in df.columns:
                    cat_options = ["All"] + sorted([x for x in df["Category"].dropna().unique() if x])
                    sel_cat = st.selectbox("Category", cat_options, label_visibility="collapsed")
                else:
                    sel_cat = "All"

            if search:
                mask = df.apply(lambda r: r.astype(str).str.contains(search, case=False).any(), axis=1)
                df = df[mask]
            if sel_cat != "All" and "Category" in df.columns:
                df = df[df["Category"] == sel_cat]

            st.caption(f"Showing **{len(df)}** of {len(items_df)} items")

            # Card Gallery
            if view_mode == "🃏 Card Gallery":
                n = 3
                for i in range(0, len(df), n):
                    chunk = df.iloc[i:i+n]
                    cols = st.columns(n)
                    for ci, (_, item) in enumerate(chunk.iterrows()):
                        with cols[ci]:
                            img_url = str(item.get("Image URL",""))
                            title   = str(item.get("Title","—"))[:90]
                            price   = str(item.get("Price",""))
                            rating  = str(item.get("Rating",""))
                            desc    = str(item.get("Description",""))[:180]
                            url     = str(item.get("URL",""))
                            cat     = str(item.get("Category",""))
                            brand   = str(item.get("Brand",""))
                            avail   = str(item.get("Availability",""))
                            sku     = str(item.get("SKU / ID",""))

                            img_html  = f'<img src="{img_url}" style="width:100%;height:175px;object-fit:cover;border-radius:12px 12px 0 0;display:block;" onerror="this.style.display=\'none\'">' if img_url else '<div style="width:100%;height:80px;background:rgba(124,156,255,0.07);border-radius:12px 12px 0 0;display:flex;align-items:center;justify-content:center;font-size:2rem;">📦</div>'
                            cat_html  = f'<span class="cat-pill">{cat}</span>' if cat and cat != "nan" else ""
                            brand_html= f'<span style="font-size:.72rem;color:#9aa4c7;">by {brand}</span>' if brand and brand != "nan" else ""
                            price_html= f'<div class="product-price">{price}</div>' if price and price != "nan" else ""
                            rate_html = f'<div class="product-rating">⭐ {rating}</div>' if rating and rating != "nan" else ""
                            avail_html= f'<div style="font-size:.72rem;color:#28c840;">{avail}</div>' if avail and avail != "nan" else ""
                            sku_html  = f'<div style="font-size:.68rem;color:#9aa4c7;">SKU: {sku}</div>' if sku and sku != "nan" else ""
                            desc_html = f'<div class="product-desc">{desc}</div>' if desc and desc != "nan" else ""
                            url_html  = f'<div style="margin-top:.4rem;"><a href="{url}" target="_blank" style="color:#7c9cff;font-size:.75rem;">🔗 Visit page →</a></div>' if url and url != "nan" else ""

                            st.markdown(f"""
<div class="product-card">
  {img_html}
  <div class="product-body">
    {cat_html}
    <div class="product-title">{title}</div>
    {brand_html}
    {price_html}
    {rate_html}
    {avail_html}
    {sku_html}
    {desc_html}
    {url_html}
  </div>
</div>""", unsafe_allow_html=True)

            # Table
            elif view_mode == "📋 Table":
                all_cols = list(df.columns)
                show_cols = st.multiselect("Columns to show", all_cols, default=all_cols[:10], key="vis_cols")
                view_df = df[show_cols] if show_cols else df
                # Make URL columns clickable
                col_cfg = {}
                for c in view_df.columns:
                    if "url" in c.lower():
                        col_cfg[c] = st.column_config.LinkColumn(c)
                st.dataframe(view_df, use_container_width=True, height=520, column_config=col_cfg)

            # Detail Inspector
            elif view_mode == "🔍 Detail Inspector":
                idx = st.slider("Item #", 1, max(len(df),1), 1) - 1
                item = df.iloc[idx]
                left, right = st.columns([1, 2])
                with left:
                    img_url = str(item.get("Image URL",""))
                    if img_url and img_url != "nan":
                        st.markdown(f'<img src="{img_url}" style="width:100%;border-radius:12px;border:1px solid rgba(255,255,255,0.08);" onerror="this.style.display=\'none\'">',
                                    unsafe_allow_html=True)
                    else:
                        st.markdown('<div style="width:100%;height:200px;background:rgba(124,156,255,0.07);border-radius:12px;display:flex;align-items:center;justify-content:center;font-size:3.5rem;">📦</div>', unsafe_allow_html=True)
                with right:
                    rows_html = ""
                    for col, val in item.items():
                        val_str = str(val)
                        if not val_str or val_str in ["nan","","None"]:
                            continue
                        if col == "Image URL":
                            continue
                        if col == "URL":
                            val_str = f'<a href="{val_str}" target="_blank" style="color:#7c9cff;">{val_str[:80]}</a>'
                        rows_html += f"<tr><td>{col}</td><td>{val_str}</td></tr>"
                    st.markdown(f'<table class="detail-table"><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)

        else:
            st.info("No repeating cards/items found. Try a product listing, news, or directory page.")

    # ── TAB 2: Images ────────────────────────────────────────────────────────
    with tabs[1]:
        imgs = st.session_state.images
        if imgs:
            st.markdown(f"### 🖼️ {len(imgs)} Images Extracted")

            # Filter controls
            fc1, fc2 = st.columns([3,2])
            with fc1:
                img_filter = st.text_input("Filter URLs", placeholder="jpg, png, logo, product...", label_visibility="collapsed")
            with fc2:
                img_cols = st.select_slider("Columns", options=[2,3,4,5,6], value=4)

            display = [i for i in imgs if img_filter.lower() in i["Image URL"].lower()] if img_filter else imgs
            display = display[:max_img_preview]
            st.caption(f"Showing {len(display)} of {len(imgs)}")

            # Grid
            for row_start in range(0, len(display), img_cols):
                row_imgs = display[row_start:row_start+img_cols]
                cols = st.columns(img_cols)
                for ci, img_data in enumerate(row_imgs):
                    with cols[ci]:
                        url = img_data["Image URL"]
                        alt = img_data.get("Alt Text","")
                        fname = url.split("?")[0].split("/")[-1][:32]
                        st.markdown(f"""
<div style="margin-bottom:.8rem;">
  <img src="{url}" style="width:100%;height:130px;object-fit:cover;border-radius:8px;border:1px solid rgba(255,255,255,0.06);display:block;" onerror="this.style.display='none'">
  <div style="font-size:.65rem;color:#7c9cff;margin-top:3px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;" title="{alt}">{alt or fname}</div>
</div>""", unsafe_allow_html=True)

            # Full table
            with st.expander(f"📋 All {len(imgs)} image URLs & details"):
                img_df = pd.DataFrame(imgs)
                st.dataframe(img_df, use_container_width=True, height=300,
                             column_config={"Image URL": st.column_config.LinkColumn("Image URL")})

            # Downloads
            img_df_full = pd.DataFrame(imgs)
            c1, c2 = st.columns(2)
            c1.download_button("⬇️ CSV — All Images", img_df_full.to_csv(index=False).encode(), "aura_images.csv", "text/csv")
            c2.download_button("⬇️ JSON — All Images", img_df_full.to_json(orient="records",indent=2).encode(), "aura_images.json", "application/json")
        else:
            st.info("No images found (or image extraction disabled).")

    # ── TAB 3: Tables ────────────────────────────────────────────────────────
    with tabs[2]:
        tables = st.session_state.tables
        if tables:
            st.markdown(f"### 📊 {len(tables)} HTML Table(s)")
            for i, t in enumerate(tables):
                with st.expander(f"Table {i+1} — {len(t)} rows × {len(t.columns)} columns", expanded=(i==0)):
                    st.dataframe(t, use_container_width=True, height=300)
                    c1,c2,c3 = st.columns(3)
                    c1.download_button("⬇️ CSV", t.to_csv(index=False).encode(), f"table_{i+1}.csv", "text/csv", key=f"tcsv{i}")
                    c2.download_button("⬇️ JSON", t.to_json(orient="records",indent=2).encode(), f"table_{i+1}.json", "application/json", key=f"tjsn{i}")
                    try:
                        c3.download_button("⬇️ Excel", df_to_excel(t), f"table_{i+1}.xlsx",
                                           "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"txls{i}")
                    except Exception:
                        pass
        else:
            st.info("No HTML tables found.")

    # ── TAB 4: Links ─────────────────────────────────────────────────────────
    with tabs[3]:
        ldf = st.session_state.links_df
        if ldf is not None and not ldf.empty:
            st.markdown(f"### 🔗 {len(ldf)} Links")
            lsearch = st.text_input("Filter", placeholder="Search text or URL...", label_visibility="collapsed")
            disp_ldf = ldf[ldf.apply(lambda r: r.astype(str).str.contains(lsearch, case=False).any(), axis=1)] if lsearch else ldf
            st.dataframe(disp_ldf, use_container_width=True, height=420,
                         column_config={"URL": st.column_config.LinkColumn("URL")})

            c1,c2 = st.columns(2)
            c1.download_button("⬇️ CSV", disp_ldf.to_csv(index=False).encode(), "aura_links.csv", "text/csv")
            try:
                c2.download_button("⬇️ Excel", df_to_excel(disp_ldf), "aura_links.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            except Exception:
                pass

            with st.expander("🌍 Domain Breakdown"):
                dc = disp_ldf["Domain"].value_counts().reset_index()
                dc.columns = ["Domain","Links"]
                st.dataframe(dc, use_container_width=True, height=200)
        else:
            st.info("No links found.")

    # ── TAB 5: Headings ──────────────────────────────────────────────────────
    with tabs[4]:
        hdf = st.session_state.headings_df
        if hdf is not None and not hdf.empty:
            st.markdown(f"### 📝 {len(hdf)} Headings")
            level_colors = {"H1":"#7c9cff","H2":"#00e0ff","H3":"#e6ecff","H4":"#9aa4c7","H5":"#9aa4c7","H6":"#9aa4c7"}
            for level in ["H1","H2","H3","H4","H5","H6"]:
                subset = hdf[hdf["Level"]==level]
                if subset.empty:
                    continue
                color = level_colors.get(level,"#9aa4c7")
                st.markdown(f'<div class="cat-header"><span style="color:{color};font-family:Poppins,sans-serif;font-weight:700;font-size:1rem;">{level}</span><span class="cat-count">{len(subset)}</span></div>', unsafe_allow_html=True)
                for _, r in subset.iterrows():
                    size = {"H1":"1rem","H2":".9rem","H3":".85rem"}.get(level,".8rem")
                    st.markdown(f'<div style="padding:.35rem .8rem;margin-bottom:.25rem;background:rgba(18,24,38,0.5);border-radius:6px;font-size:{size};">{r["Text"]}</div>', unsafe_allow_html=True)

            st.download_button("⬇️ Download Headings CSV", hdf.to_csv(index=False).encode(), "aura_headings.csv", "text/csv")
        else:
            st.info("No headings found.")

    # ── TAB 6: Meta ──────────────────────────────────────────────────────────
    with tabs[5]:
        meta = st.session_state.meta
        if meta:
            st.markdown("### 🏷️ Page Metadata")
            rows_html = "".join(f"<tr><td>{k}</td><td>{str(v)[:400]}</td></tr>" for k,v in meta.items() if v)
            st.markdown(f'<table class="detail-table"><thead><tr><th>Field</th><th>Value</th></tr></thead><tbody>{rows_html}</tbody></table>', unsafe_allow_html=True)
            meta_df = pd.DataFrame(list(meta.items()), columns=["Field","Value"])
            st.download_button("⬇️ Download Meta CSV", meta_df.to_csv(index=False).encode(), "aura_meta.csv", "text/csv")
        else:
            st.info("No metadata found.")

    # ── TAB 7: Export All ────────────────────────────────────────────────────
    with tabs[6]:
        st.markdown("### 📥 Export All Categories")

        def export_block(label, df_exp, prefix):
            if df_exp is None or df_exp.empty:
                return
            st.markdown(f"**{label}** — {len(df_exp):,} rows · {len(df_exp.columns)} columns")
            c1,c2,c3 = st.columns(3)
            c1.download_button("⬇️ CSV", df_exp.to_csv(index=False).encode(), f"aura_{prefix}.csv", "text/csv", key=f"xc_{prefix}")
            c2.download_button("⬇️ JSON", df_exp.to_json(orient="records",indent=2).encode(), f"aura_{prefix}.json", "application/json", key=f"xj_{prefix}")
            try:
                c3.download_button("⬇️ Excel", df_to_excel(df_exp), f"aura_{prefix}.xlsx",
                                   "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key=f"xx_{prefix}")
            except Exception as e:
                c3.caption(f"Excel n/a: {e}")
            st.markdown('<hr class="aura-divider">', unsafe_allow_html=True)

        export_block("🃏 Items / Cards", st.session_state.items_df, "items")
        if st.session_state.images:
            export_block("🖼️ Images", pd.DataFrame(st.session_state.images), "images")
        if st.session_state.links_df is not None:
            export_block("🔗 Links", st.session_state.links_df, "links")
        if st.session_state.headings_df is not None:
            export_block("📝 Headings", st.session_state.headings_df, "headings")
        for i, t in enumerate(st.session_state.tables or []):
            export_block(f"📊 Table {i+1}", t, f"table_{i+1}")
        if st.session_state.meta:
            export_block("🏷️ Meta", pd.DataFrame(list(st.session_state.meta.items()), columns=["Field","Value"]), "meta")

# ─────────────────────────────────────────────────────────────────────────────
# EMPTY STATE
# ─────────────────────────────────────────────────────────────────────────────
elif not extract_btn:
    st.markdown("""
<div class="glass-card" style="text-align:center;padding:3rem 2rem;margin-bottom:1.5rem;">
  <div style="font-size:3.5rem;margin-bottom:1rem;">🔵</div>
  <div style="font-family:Poppins,sans-serif;font-size:1.3rem;font-weight:700;margin-bottom:.5rem;">
    Ready to extract everything
  </div>
  <div style="color:#9aa4c7;">
    Paste any URL above. AURA extracts images, products/cards, tables, links, headings<br>and page metadata — all organized into separate, downloadable categories.
  </div>
</div>
""", unsafe_allow_html=True)

    cols = st.columns(4)
    tiles = [
        ("🖼️","Images","Every image URL with alt text, width, height — filterable gallery + CSV/JSON export."),
        ("🃏","Products & Cards","Title · Price · Rating · Description · Image · URL · Brand · SKU · Availability — card + table + inspector views."),
        ("📊","HTML Tables","All <table> elements converted to clean DataFrames with individual downloads."),
        ("🔗","Links & Meta","All hyperlinks with domain breakdown, plus full page metadata and headings tree."),
    ]
    for col, (icon, title, desc) in zip(cols, tiles):
        with col:
            st.markdown(f'<div class="glass-card" style="text-align:center;height:100%;"><div style="font-size:2.2rem;margin-bottom:.5rem;">{icon}</div><div style="font-family:Poppins,sans-serif;font-weight:700;margin-bottom:.4rem;">{title}</div><div style="color:#9aa4c7;font-size:.8rem;line-height:1.5;">{desc}</div></div>', unsafe_allow_html=True)
