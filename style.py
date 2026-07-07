import streamlit as st
import streamlit as st
import base64

# Streamlit's st.markdown renders through a Markdown parser: any line with
# 4+ leading spaces is treated as an indented code block and shown as raw
# text instead of being rendered as HTML. The SVG/HTML builders below are
# written as indented Python triple-quoted strings for readability, so every
# returned snippet is passed through this to strip that leading whitespace
# before it goes to st.markdown.
def _flatten(html: str) -> str:
    return "\n".join(line.strip() for line in html.strip().splitlines())


# ---------------------------------------------------------------------------
# CMart Solutions brand palette, pulled directly from the logo:
#   navy line/wordmark  -> #0A2A45
#   secondary navy      -> #0F3B62
#   primary accent blue -> #429EDE
#   light accent blue   -> #B5DBF6
# ---------------------------------------------------------------------------
BRAND = {
    "navy": "#0A2A45",
    "navy_deep": "#071B2E",
    "navy_mid": "#0F3B62",
    "blue": "#429EDE",
    "blue_light": "#B5DBF6",
}

# Severity keeps a semantic red -> amber -> blue -> grey ramp so urgency is
# still readable at a glance; High/Medium are tuned toward the brand blue
# family instead of the old neutral gold/steel.
SEVERITY_COLORS = {
    "Critical": "#C0524A",
    "High": "#D98B3F",
    "Medium": "#429EDE",
    "Low": "#4F6070",
}

CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600&family=Inter:wght@400;500;600;700&display=swap');

html, body, [class*="css"]  {{
    font-family: 'Inter', sans-serif;
}}

.block-container {{
    padding-top: 3.6rem;
    max-width: 1180px;
}}

/* Streamlit's fixed header bar sits above the content at z-index above
   the block-container on some Community Cloud / recent Streamlit builds,
   which is what was clipping the page title. Keep it transparent and
   out of the way instead of removing it (removing it drops the
   hamburger menu / rerun controls). */
[data-testid="stHeader"] {{
    background: transparent;
    height: 2.6rem;
}}

/* section framing line under page titles */
.page-kicker-row {{
    display: flex;
    align-items: center;
    gap: 0.5rem;
}}

.page-kicker {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    color: {BRAND['blue_light']};
    margin-bottom: 0.15rem;
}}

.page-title-row {{
    display: flex;
    align-items: center;
    gap: 0.55rem;
}}

.page-title {{
    font-size: 1.65rem;
    font-weight: 700;
    color: #E7E9EC;
    margin-bottom: 0.15rem;
}}

.page-frame {{
    font-size: 0.92rem;
    color: #9BA6B5;
    border-left: 2px solid {BRAND['blue']};
    padding-left: 0.7rem;
    margin: 0.6rem 0 1.6rem 0;
}}

/* metric stat blocks -- small mascot icon in the corner, still plain
   otherwise (no gauges / speedometers) */
.stat-row {{
    display: flex;
    gap: 0.9rem;
    flex-wrap: wrap;
    margin-bottom: 1.2rem;
}}
.stat-block {{
    position: relative;
    background: #161E2E;
    border: 1px solid #24304A;
    border-radius: 6px;
    padding: 0.85rem 1.1rem;
    flex: 1;
    min-width: 150px;
    overflow: hidden;
}}
.stat-icon {{
    position: absolute;
    top: 0.55rem;
    right: 0.6rem;
    opacity: 0.9;
}}
.stat-label {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.68rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: {BRAND['blue_light']};
    margin-bottom: 0.3rem;
    padding-right: 1.6rem;
}}
.stat-value {{
    font-size: 1.55rem;
    font-weight: 600;
    color: #E7E9EC;
    font-variant-numeric: tabular-nums;
}}
.stat-sub {{
    font-size: 0.75rem;
    color: #6E7A8A;
    margin-top: 0.15rem;
}}

.severity-pill {{
    display: inline-block;
    padding: 0.12rem 0.55rem;
    border-radius: 999px;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}}

hr.section-rule {{
    border: none;
    border-top: 1px solid #24304A;
    margin: 1.6rem 0 1.2rem 0;
}}

.footnote {{
    font-size: 0.76rem;
    color: #5C6779;
    margin-top: 2rem;
}}

/* dataframe tightening */
[data-testid="stDataFrame"] {{
    border: 1px solid #24304A;
    border-radius: 6px;
}}
</style>
"""


def inject():
    st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Brand mark -- the CMart diamond, recreated as inline SVG so it's crisp
# at any size and themeable (used next to the page title).
# ---------------------------------------------------------------------------
def brand_mark_svg(size: int = 30) -> str:
    with open("cmart_logo.png", "rb") as f:
        logo = base64.b64encode(f.read()).decode()

    return f"""
    <img src="data:image/png;base64,{logo}"
         width="{size*4}"
         style="vertical-align: middle;">
    """
# ---------------------------------------------------------------------------
# Mascot icons -- a small recurring "diamond buddy" character (echoing the
# brand mark) holding a different prop per stat card. Flat line style,
# two-tone brand blues, kept subtle enough for an ops console.
# ---------------------------------------------------------------------------
def _mascot_base(prop_svg: str, size: int = 34) -> str:
    return _flatten(f"""
    <svg class="stat-icon" width="{size}" height="{size}" viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg">
        <!-- diamond head -->
        <path d="M24 6 L38 20 L24 34 L10 20 Z" fill="{BRAND['navy_mid']}" fill-opacity="0.35"
              stroke="{BRAND['blue_light']}" stroke-width="1.6"/>
        <!-- eyes -->
        <circle cx="19.5" cy="19" r="1.7" fill="{BRAND['blue_light']}"/>
        <circle cx="28.5" cy="19" r="1.7" fill="{BRAND['blue_light']}"/>
        <!-- smile -->
        <path d="M19 24 Q24 27.5 29 24" stroke="{BRAND['blue_light']}" stroke-width="1.4"
              fill="none" stroke-linecap="round"/>
        {prop_svg}
    </svg>
    """)


def mascot_svg(kind: str, size: int = 34) -> str:
    """kind: 'briefcase' | 'magnifier' | 'coins' | 'shield'"""
    props = {
        "briefcase": f"""
            <rect x="16" y="35" width="16" height="8" rx="1.4" fill="none"
                  stroke="{BRAND['blue']}" stroke-width="2"/>
            <path d="M20 35 v-2.5 a2 2 0 0 1 2 -2 h4 a2 2 0 0 1 2 2 v2.5"
                  fill="none" stroke="{BRAND['blue']}" stroke-width="2"/>
        """,
        "magnifier": f"""
            <circle cx="31" cy="36" r="5" fill="none" stroke="{BRAND['blue']}" stroke-width="2"/>
            <line x1="34.6" y1="39.6" x2="39" y2="44" stroke="{BRAND['blue']}" stroke-width="2.2"
                  stroke-linecap="round"/>
        """,
        "coins": f"""
            <ellipse cx="17" cy="40" rx="6" ry="3" fill="none" stroke="{BRAND['blue']}" stroke-width="1.8"/>
            <ellipse cx="24" cy="36.5" rx="6" ry="3" fill="none" stroke="{BRAND['blue']}" stroke-width="1.8"/>
            <ellipse cx="31" cy="40" rx="6" ry="3" fill="{BRAND['blue']}" fill-opacity="0.25"
                     stroke="{BRAND['blue']}" stroke-width="1.8"/>
        """,
        "shield": f"""
            <path d="M24 33 L31 35.5 V41 C31 44.5 27.8 46.6 24 48 C20.2 46.6 17 44.5 17 41 V35.5 Z"
                  transform="translate(0,-6)"
                  fill="{BRAND['blue']}" fill-opacity="0.2" stroke="{BRAND['blue']}" stroke-width="1.8"/>
            <line x1="24" y1="34" x2="24" y2="38.5" stroke="{BRAND['blue']}" stroke-width="1.8"
                  stroke-linecap="round"/>
            <circle cx="24" cy="41" r="0.9" fill="{BRAND['blue']}"/>
        """,
    }
    return _mascot_base(props.get(kind, ""), size=size)


def page_header(kicker: str, title: str, framing: str):
    st.markdown(
        f'<div class="page-kicker-row">{brand_mark_svg(12)}'
        f'<div class="page-kicker">{kicker}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="page-title-row">{brand_mark_svg(18)}'
        f'<div class="page-title">{title}</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(f'<div class="page-frame">{framing}</div>', unsafe_allow_html=True)


def stat_block_html(label: str, value: str, sub: str = "", icon: str = "") -> str:
    sub_html = f'<div class="stat-sub">{sub}</div>' if sub else ""
    icon_html = mascot_svg(icon) if icon else ""
    return _flatten(f"""
    <div class="stat-block">
        {icon_html}
        <div class="stat-label">{label}</div>
        <div class="stat-value">{value}</div>
        {sub_html}
    </div>
    """)


def severity_pill(severity: str) -> str:
    color = SEVERITY_COLORS.get(severity, "#429EDE")
    return f'<span class="severity-pill" style="background:{color}22;color:{color};border:1px solid {color}55;">{severity}</span>'


def fmt_usd(x) -> str:
    try:
        return f"${x:,.0f}"
    except (TypeError, ValueError):
        return "-"


def fmt_pct(x) -> str:
    try:
        return f"{x:.1f}%"
    except (TypeError, ValueError):
        return "-"
