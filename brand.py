"""The shared look of Bikash Kushwaha's project demos: page setup, top bar, hero and footer.

The same file is copied into every project, so all the demos read as one portfolio. Use it as
the first Streamlit call in app.py:

    import brand

    brand.page("hawa")
    ...
    brand.footer()
"""

from __future__ import annotations

from html import escape

import streamlit as st

OWNER = "Bikash Kushwaha"
ROLE = "Machine learning and cloud engineer, Nepal"
HUB = "https://bikash9cmd-portfolio.onrender.com"
GITHUB = "https://github.com/bikash9cmd"
LINKEDIN = "https://www.linkedin.com/in/bikash9cmd"

# key: (name, Nepali, area, one line, repo, Material icon)
PROJECTS = {
    "hawa": (
        "Hawa",
        "हावा",
        "Machine learning",
        "Hour-by-hour PM2.5 forecasts and health alerts for the Kathmandu Valley.",
        "hawa-kathmandu-air",
        "air",
    ),
    "bijuli": (
        "Bijuli",
        "बिजुली",
        "MLOps",
        "Day-ahead electricity demand forecasts for Nepal's grid, kept good for years.",
        "bijuli-nepal-grid-forecast",
        "bolt",
    ),
    "chowk": (
        "Chowk",
        "चोक",
        "Computer vision",
        "Vehicle-mix traffic counts for Kathmandu junctions, in passenger car units.",
        "chowk-kathmandu-traffic",
        "traffic",
    ),
    "pahiro": (
        "Pahiro",
        "पहिरो",
        "Machine learning",
        "Landslide early warning for Nepal's central hills.",
        "pahiro-nepal-landslide",
        "terrain",
    ),
    "barsha": (
        "Barsha",
        "वर्षा",
        "Data engineering",
        "Fifty years of Nepal's rainfall in a lakehouse, with a daily bulletin.",
        "barsha-nepal-monsoon-lakehouse",
        "rainy",
    ),
    "fohor": (
        "Fohor",
        "फोहोर",
        "Data engineering",
        "Where the Kathmandu Valley's waste goes, and what a landfill blockade does.",
        "fohor-kathmandu-waste",
        "recycling",
    ),
    "bhuktani": (
        "Bhuktani",
        "भुक्तानी",
        "Streaming data",
        "Real-time QR payments lakehouse that catches money stuck between banks.",
        "bhuktani-nepal-payments-stream",
        "payments",
    ),
    "bato": (
        "Bato",
        "बाटो",
        "Cloud systems",
        "Trek check-ins that notice a missing group, and storm holds for high passes.",
        "bato-trek-safety-nepal",
        "landscape",
    ),
    "surakshit": (
        "Surakshit",
        "सुरक्षित",
        "Cloud systems",
        '"I\'m safe" check-ins for the next big earthquake in Nepal.',
        "surakshit-nepal-quake-checkin",
        "health_and_safety",
    ),
    "parkha": (
        "Parkha",
        "पर्ख",
        "AI assistant",
        "Pest advice for farmers that never skips the pre-harvest waiting period.",
        "parkha-nepal-safe-harvest",
        "eco",
    ),
    "sodhnus": (
        "Sodhnus",
        "सोध्नुस्",
        "AI assistant",
        "Rainfall questions about Nepal, answered only from verified data.",
        "sodhnus-nepal-rain-assistant",
        "forum",
    ),
    "kagaj": (
        "Kagaj",
        "कागज",
        "AI agent",
        "Government papers in Nepal: what to bring, what it costs, every fee cited.",
        "kagaj-nepal-docs",
        "description",
    ),
    "gopya": (
        "Gopya",
        "गोप्य",
        "AI assistant",
        "A company assistant that only knows what your role is allowed to know.",
        "gopya-company-rag",
        "lock",
    ),
    "chhanot": (
        "Chhanot",
        "छनोट",
        "Machine learning",
        "Support ticket triage that knows what it mustn't handle alone.",
        "chhanot-ticket-triage",
        "inbox",
    ),
    "ghanti": (
        "Ghanti",
        "घण्टी",
        "Voice AI",
        "A phone agent for an internet provider that knows when to hand over.",
        "ghanti-isp-voice-agent",
        "call",
    ),
}

CSS = """
<style>
:root {
  --bk-ink: #0B1220; --bk-muted: #5B6474; --bk-line: #E6E8EE; --bk-surface: #F6F7F9;
  --bk-accent: #2346D8; --bk-accent-soft: #EEF2FF; --bk-crimson: #D7263D;
}
#MainMenu, footer, .stDeployButton, [data-testid="stToolbar"], [data-testid="stDecoration"] {
  display: none !important;
}
header[data-testid="stHeader"] { background: transparent; height: 2.5rem; }
.block-container { max-width: 1180px; padding-top: 1.5rem; padding-bottom: 2rem; }
h1, h2, h3 { letter-spacing: -0.02em; color: var(--bk-ink); }
.bk-nav a, .bk-actions a, .bk-footer a { text-decoration: none !important; }
.bk-nav {
  display: flex; align-items: center; justify-content: space-between; gap: 1rem;
  padding-bottom: 1rem; border-bottom: 1px solid var(--bk-line); margin-bottom: 2.25rem;
}
.bk-brand { display: flex; align-items: center; gap: .65rem; color: var(--bk-ink) !important; }
.bk-mark {
  width: 32px; height: 32px; border-radius: 9px; display: grid; place-items: center;
  background: linear-gradient(135deg, var(--bk-crimson), #8E1B5A 55%, var(--bk-accent));
  color: #fff; font-weight: 700; font-size: .8rem; letter-spacing: .02em;
}
.bk-brand b { font-weight: 650; font-size: .98rem; }
.bk-brand span { color: var(--bk-muted); font-size: .85rem; }
.bk-links { display: flex; gap: .4rem; flex-wrap: wrap; }
.bk-links a, .bk-btn {
  font-size: .85rem; font-weight: 550; padding: .42rem .8rem; border-radius: 8px;
  border: 1px solid var(--bk-line); color: var(--bk-ink) !important; background: #fff;
}
.bk-links a:hover, .bk-btn:hover { border-color: #C9CEDA; background: var(--bk-surface); }
.bk-btn.primary { background: var(--bk-ink); border-color: var(--bk-ink); color: #fff !important; }
.bk-btn.primary:hover { background: #222B3D; }
.bk-kicker { display: flex; align-items: center; gap: .6rem; margin-bottom: .75rem; flex-wrap: wrap; }
.bk-live {
  display: inline-flex; align-items: center; gap: .4rem; font-size: .75rem; font-weight: 600;
  color: #0A7A3E; background: #E9F7EF; border: 1px solid #CBEBD8;
  padding: .2rem .55rem; border-radius: 999px;
}
.bk-live::before { content: ""; width: 6px; height: 6px; border-radius: 50%; background: #16A34A; }
.bk-eyebrow {
  font-size: .78rem; font-weight: 650; letter-spacing: .08em; text-transform: uppercase;
  color: var(--bk-accent);
}
.bk-title {
  font-size: 2.75rem; line-height: 1.1; font-weight: 700; letter-spacing: -0.035em; margin: 0;
  color: var(--bk-ink) !important;
}
.bk-title span { color: #9AA1AE; font-weight: 500; margin-left: .75rem; letter-spacing: 0; }
.bk-lede {
  font-size: 1.12rem; line-height: 1.55; color: var(--bk-muted) !important; max-width: 46rem;
  margin: 1rem 0 1.4rem !important;
}
.bk-actions { display: flex; gap: .5rem; flex-wrap: wrap; margin-bottom: 2rem; }
.bk-note {
  font-size: .85rem; color: var(--bk-muted); background: var(--bk-surface);
  border: 1px solid var(--bk-line); border-radius: 10px; padding: .6rem .85rem; margin-bottom: 1.5rem;
}
[data-testid="stMetric"] {
  background: #fff; border: 1px solid var(--bk-line); border-radius: 12px; padding: .9rem 1rem;
}
[data-testid="stMetricLabel"] p { color: var(--bk-muted); font-size: .82rem; }
[data-testid="stSidebar"] { background: var(--bk-surface); border-right: 1px solid var(--bk-line); }
[data-testid="stSidebar"] .stButton button { justify-content: flex-start; padding: .55rem .8rem; }
[data-testid="stSidebar"] .stButton button div { justify-content: flex-start; }
[data-testid="stSidebar"] .stButton button p { text-align: left; font-size: .88rem; }
[data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
  font-size: .78rem; text-transform: uppercase; letter-spacing: .08em; color: var(--bk-muted);
}
[data-testid="stChatMessageAvatarUser"], [data-testid="stChatMessageAvatarAssistant"],
[data-testid="stChatMessageAvatarCustom"] {
  background: var(--bk-surface); color: var(--bk-ink); border: 1px solid var(--bk-line);
}
.stTabs [data-baseweb="tab-list"] { gap: 1.5rem; border-bottom: 1px solid var(--bk-line); }
.stTabs [data-baseweb="tab"] { padding-left: 0; padding-right: 0; font-weight: 550; }
[data-testid="stChatMessage"] { background: transparent; border-bottom: 1px solid var(--bk-line); border-radius: 0; }
[data-testid="stDataFrame"], [data-testid="stCode"] { border-radius: 10px; }
.bk-footer {
  margin-top: 4rem; padding-top: 1.5rem; border-top: 1px solid var(--bk-line);
  display: flex; justify-content: space-between; gap: 1rem; flex-wrap: wrap;
  font-size: .85rem; color: var(--bk-muted);
}
.bk-footer b { color: var(--bk-ink); font-weight: 600; }
.bk-footer a { color: var(--bk-muted) !important; margin-left: 1rem; }
.bk-footer a:hover { color: var(--bk-ink) !important; }
@media (max-width: 640px) {
  .bk-title { font-size: 2rem; } .bk-brand span { display: none; } .bk-links a.bk-hide { display: none; }
}
</style>
"""


def _html(markup: str) -> None:
    # One line per element: Markdown would treat indented HTML as a code block.
    st.markdown("".join(line.strip() for line in markup.splitlines()), unsafe_allow_html=True)


def page(key: str, layout: str = "wide", note: str | None = None) -> None:
    """Page config, the shared stylesheet, the top bar and the project's hero. Call it first."""
    name, nepali, area, line, repo, icon = PROJECTS[key]
    st.set_page_config(page_title=f"{name} · {OWNER}", page_icon=f":material/{icon}:", layout=layout)
    st.markdown(CSS, unsafe_allow_html=True)
    _html(f"""
        <div class="bk-nav">
          <a class="bk-brand" href="{HUB}"><div class="bk-mark">BK</div><b>{OWNER}</b><span>{ROLE}</span></a>
          <div class="bk-links">
            <a href="{HUB}">All projects</a>
            <a class="bk-hide" href="{GITHUB}" target="_blank">GitHub</a>
            <a class="bk-hide" href="{LINKEDIN}" target="_blank">LinkedIn</a>
          </div>
        </div>
        <div class="bk-kicker">
          <span class="bk-eyebrow">{escape(area)}</span><span class="bk-live">Live demo</span>
        </div>
        <div class="bk-title">{name}<span>{nepali}</span></div>
        <p class="bk-lede">{escape(line)}</p>
        <div class="bk-actions">
          <a class="bk-btn primary" href="{GITHUB}/{repo}" target="_blank">View the code</a>
          <a class="bk-btn" href="{GITHUB}/{repo}#readme" target="_blank">How it works</a>
        </div>
    """)
    if note:
        _html(f'<div class="bk-note">{escape(note)}</div>')


def avatar(role: str, key: str) -> str:
    """Chat avatars in the brand's style: a person for the user, the project's icon for the assistant."""
    return ":material/person:" if role == "user" else f":material/{PROJECTS[key][5]}:"


def footer() -> None:
    year = 2026
    _html(f"""
        <div class="bk-footer">
          <div><b>{OWNER}</b> · {ROLE} · {year}</div>
          <div><a href="{HUB}">All projects</a><a href="{GITHUB}" target="_blank">GitHub</a>
          <a href="{LINKEDIN}" target="_blank">LinkedIn</a></div>
        </div>
    """)
