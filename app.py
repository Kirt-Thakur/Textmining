from pathlib import Path
from urllib.parse import urlparse, urljoin
import hashlib
import ipaddress
import pickle
import re
import socket

import pandas as pd
import pymupdf
import requests
import streamlit as st

from fintech_dictionary import FINTECH_DICTIONARY
from index_calculator import analyse_report_text


# ============================================================
# 1. SETTINGS
# ============================================================

st.set_page_config(
    page_title="FinTech Adoption Dashboard",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded",
)

NAVY = "#14243B"
TEAL = "#0D9488"
WHITE = "#FFFFFF"
BLACK = "#111827"
LIGHT_BG = "#F5F7FA"
BORDER = "#D8E0E8"

FINANCIAL_YEARS = [f"{y}-{str(y + 1)[-2:]}" for y in range(2015, 2026)]

# Blockchain is tracked separately in the calculator, if present.
PARAMETERS = [
    p for p in FINTECH_DICTIONARY.keys() if "blockchain" not in p.lower()
]
MAX_SCORE = len(PARAMETERS)

MAX_PDF_BYTES = 150 * 1024 * 1024      # 150 MB download cap
MAX_REDIRECTS = 5
RESULTS_FILE = Path("fintech_results.pkl")

KNOWN_ACRONYMS = {
    "sbi", "icici", "hdfc", "pnb", "idbi", "uco", "iob", "bob", "idfc",
    "au", "csb", "dcb", "rbl", "hsbc", "dbs", "ubi", "boi", "bom", "yes",
}
LOWER_WORDS = {"of", "and", "the", "for"}


# ============================================================
# 2. STYLE
# ============================================================

st.markdown(
    f"""
    <style>
    .stApp {{ background-color: {LIGHT_BG}; color: {BLACK}; }}
    [data-testid="stSidebar"] {{ background-color: {NAVY}; }}
    [data-testid="stSidebar"] * {{ color: {WHITE}; }}
    [data-testid="stSidebar"] input,
    [data-testid="stSidebar"] textarea {{
        color: {BLACK} !important; background-color: {WHITE} !important;
    }}
    [data-testid="stSidebar"] [data-baseweb="select"] * {{ color: {BLACK} !important; }}
    [data-testid="stSidebar"] [data-baseweb="select"] > div {{
        background-color: {WHITE} !important;
    }}
    h1, h2, h3, h4 {{ color: {NAVY} !important; }}
    p, label, .stMarkdown, .stCaption {{ color: {BLACK}; }}
    [data-testid="stMetric"] {{
        background-color: {WHITE}; border: 1px solid {BORDER};
        border-radius: 12px; padding: 15px;
    }}
    [data-testid="stMetricLabel"] {{ color: {BLACK} !important; }}
    [data-testid="stMetricValue"] {{ color: {NAVY} !important; }}
    .hero {{
        background: linear-gradient(120deg, {NAVY}, #203D5B);
        padding: 26px 30px; border-radius: 16px; margin-bottom: 22px;
    }}
    .hero h1 {{ color: {WHITE} !important; margin: 0; font-size: 30px; }}
    .hero p {{ color: {WHITE} !important; margin: 8px 0 0 0; font-size: 15px; }}
    div.stButton > button {{
        background-color: {TEAL}; color: {WHITE}; border: none;
        border-radius: 8px; font-weight: 600;
    }}
    div.stButton > button:hover {{ background-color: {NAVY}; color: {WHITE}; border: none; }}
    div[data-testid="stDownloadButton"] button {{
        background-color: {NAVY}; color: {WHITE}; border-radius: 8px;
    }}
    input, textarea {{ color: {BLACK} !important; }}
    [data-baseweb="select"] > div {{ background-color: {WHITE}; color: {BLACK}; }}
    [data-baseweb="popover"] *, [role="listbox"] *, [role="option"] {{
        color: {BLACK} !important; background-color: {WHITE};
    }}
    hr {{ border-color: {BORDER}; }}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
        <h1>FinTech Adoption Dashboard</h1>
        <p>A keyword-based analysis of FinTech-related disclosures
        in Indian bank annual reports.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 3. BANK NAME AND FINANCIAL YEAR DETECTION
# ============================================================

REPORT_WORDS = (
    r"annual\s+report|annual|report|financial\s+statements|financial|"
    r"statements|statement|audited|consolidated|standalone|year|fy|ar|"
    r"final|updated|revised|scan|copy|pvt|ltd|limited"
)


def clean_bank_name(name):
    """Clean a bank name extracted from a filename."""
    name = re.sub(r"\.pdf$", "", name, flags=re.IGNORECASE)
    name = re.sub(r"[_\-]+", " ", name)
    name = re.sub(rf"\b({REPORT_WORDS})\b", " ", name, flags=re.IGNORECASE)
    name = re.sub(r"\s+", " ", name).strip(" .-_")

    formatted = []
    for i, word in enumerate(name.split()):
        low = word.lower()
        if low in KNOWN_ACRONYMS and len(name.split()) > 1 or low in {"sbi", "icici", "hdfc", "pnb", "idbi", "uco"}:
            formatted.append(word.upper())
        elif low in LOWER_WORDS and i > 0:
            formatted.append(low)
        else:
            formatted.append(word.capitalize())

    return " ".join(formatted).strip()


def detect_bank_and_year(filename):
    """
    Detect bank name and financial year from a PDF filename.
    A standalone year such as 2020 is read as FY 2019-20.
    A range such as 2019-2023 is NOT guessed; the user must choose.
    """
    original = Path(filename).stem
    working = original
    detected_year = None
    range_seen = False

    range_match = re.search(
        r"(?<!\d)(20\d{2})\s*[-_/]\s*(\d{2}|20\d{2})(?!\d)", working
    )

    if range_match:
        range_seen = True
        start_year = int(range_match.group(1))
        end_part = range_match.group(2)

        if len(end_part) == 2:
            end_year = (start_year // 100) * 100 + int(end_part)
            if end_year < start_year:
                end_year += 100
        else:
            end_year = int(end_part)

        if end_year == start_year + 1:
            detected_year = f"{start_year}-{str(end_year)[-2:]}"

        working = working[:range_match.start()] + " " + working[range_match.end():]

    if detected_year is None and not range_seen:
        single = re.search(r"(?<!\d)(20\d{2})(?!\d)", working)
        if single:
            year = int(single.group(1))
            if year >= 2016:
                detected_year = f"{year - 1}-{str(year)[-2:]}"
                working = working[:single.start()] + " " + working[single.end():]

    bank_name = clean_bank_name(working) or clean_bank_name(original)
    return bank_name, detected_year


# ============================================================
# 4. HELPERS
# ============================================================

def year_sort_key(year):
    if not isinstance(year, str):
        return 0
    match = re.search(r"(20\d{2})", year)
    return int(match.group(1)) if match else 0


def get_study_years(from_year, to_year):
    start, end = year_sort_key(from_year), year_sort_key(to_year)
    return [y for y in FINANCIAL_YEARS if start <= year_sort_key(y) <= end]


def extract_pdf_text(pdf_bytes):
    parts = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as document:
        for page in document:
            parts.append(page.get_text("text"))
    return "\n".join(parts).strip()


def _host_is_public(hostname):
    """Reject hosts that resolve to private, loopback or link-local IPs."""
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast):
            return False
    return True


def get_pdf_bytes_from_url(url):
    """Download a PDF safely: public hosts only, size-capped, magic-byte check."""
    current = url.strip()
    headers = {"User-Agent": "Mozilla/5.0 FinTechResearchDashboard"}

    for _ in range(MAX_REDIRECTS + 1):
        parsed = urlparse(current)

        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Please provide a valid HTTP or HTTPS PDF URL.")
        if not _host_is_public(parsed.hostname):
            raise ValueError("This address is not allowed (private or unresolvable host).")

        response = requests.get(
            current, timeout=45, headers=headers,
            stream=True, allow_redirects=False,
        )

        if response.is_redirect or response.status_code in (301, 302, 303, 307, 308):
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ValueError("Redirect without a target.")
            current = urljoin(current, location)
            continue

        response.raise_for_status()

        declared = response.headers.get("Content-Length")
        if declared and declared.isdigit() and int(declared) > MAX_PDF_BYTES:
            response.close()
            raise ValueError("The PDF is larger than the 150 MB limit.")

        chunks, size = [], 0
        for chunk in response.iter_content(chunk_size=1024 * 256):
            size += len(chunk)
            if size > MAX_PDF_BYTES:
                response.close()
                raise ValueError("The PDF is larger than the 150 MB limit.")
            chunks.append(chunk)

        content = b"".join(chunks)
        if not content.startswith(b"%PDF"):
            raise ValueError(
                "The link did not return a PDF. Use a direct PDF download "
                "link, not a webpage that shows a PDF viewer."
            )
        return content

    raise ValueError("Too many redirects.")


def parameter_score(parameter_result):
    """Binary automatic keyword score for one parameter."""
    if not isinstance(parameter_result, dict):
        return 0

    score = parameter_result.get("provisional_score")
    if score is not None:
        try:
            return 1 if float(score) > 0 else 0
        except (TypeError, ValueError):
            pass

    try:
        return 1 if int(parameter_result.get("occurrence_count", 0)) > 0 else 0
    except (TypeError, ValueError):
        return 0


def analyse_pdf(pdf_bytes, bank_name, financial_year, source_name):
    """Extract PDF text and run the existing index calculator."""
    text_content = extract_pdf_text(pdf_bytes)

    if not text_content:
        raise ValueError(
            "No selectable text was found. This may be a scanned PDF "
            "that needs OCR before it can be analysed."
        )

    analysis = analyse_report_text(text_content)

    if not isinstance(analysis, dict) or not any(p in analysis for p in PARAMETERS):
        raise ValueError(
            "The calculator returned no results for the dictionary parameters. "
            "Check that index_calculator and fintech_dictionary use the same keys."
        )

    scores, evidence_rows, parameter_details = {}, [], []

    for parameter in PARAMETERS:
        result = analysis.get(parameter, {})
        if not isinstance(result, dict):
            result = {}

        score = parameter_score(result)
        scores[parameter] = score

        matched = result.get("matched_keywords", [])
        if not isinstance(matched, (list, tuple, set)):
            matched = []

        evidence_items = result.get("evidence", [])
        if not isinstance(evidence_items, (list, tuple)):
            evidence_items = []

        parameter_details.append({
            "Bank": bank_name,
            "Financial Year": financial_year,
            "Parameter": parameter,
            "Score": score,
            "Maximum Score": 1,
            "Keyword Occurrences": result.get("occurrence_count", 0),
            "Matched Keywords": ", ".join(map(str, matched)),
            "Review Status": result.get("review_status", "Automatic keyword result"),
        })

        if evidence_items:
            for item in evidence_items:
                if isinstance(item, dict):
                    text = (item.get("text") or item.get("evidence")
                            or item.get("context") or str(item))
                else:
                    text = str(item)
                evidence_rows.append({
                    "Bank": bank_name, "Financial Year": financial_year,
                    "Parameter": parameter, "Score": score,
                    "Evidence": text, "Source": source_name,
                })
        elif matched:
            evidence_rows.append({
                "Bank": bank_name, "Financial Year": financial_year,
                "Parameter": parameter, "Score": score,
                "Evidence": "Matched keywords: " + ", ".join(map(str, matched)),
                "Source": source_name,
            })

    total = sum(scores.values())

    return {
        "bank": bank_name,
        "year": financial_year,
        "source": source_name,
        "scores": scores,
        "total_score": total,
        "max_score": MAX_SCORE,
        "index_percentage": (total / MAX_SCORE * 100) if MAX_SCORE else 0,
        "parameter_details": parameter_details,
        "evidence_rows": evidence_rows,
        "text_length": len(text_content),
        "file_hash": hashlib.sha256(pdf_bytes).hexdigest(),
    }


def build_index_dataframe(results):
    rows = []
    for r in results:
        row = {"Bank": r["bank"], "Financial Year": r["year"]}
        for p in PARAMETERS:
            row[p] = r["scores"].get(p, 0)
        row["Overall Score"] = r["total_score"]
        row["Maximum Score"] = r["max_score"]
        row["Index Percentage (%)"] = round(r["index_percentage"], 2)
        row["Source"] = r["source"]
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["_y"] = df["Financial Year"].map(year_sort_key)
    df["_b"] = df["Bank"].str.lower()
    return (df.sort_values(["_y", "_b"])
              .drop(columns=["_y", "_b"])
              .reset_index(drop=True))


def combine_detail_rows(results, key):
    rows = []
    for r in results:
        rows.extend(r.get(key, []))
    return pd.DataFrame(rows)


def make_csv(df):
    return df.to_csv(index=False).encode("utf-8-sig")


def show_table(df, height=420):
    if df is None or df.empty:
        st.info("No data is available for this selection yet.")
        return
    st.dataframe(df, use_container_width=True, height=height, hide_index=True)


def save_results(results):
    try:
        with open(RESULTS_FILE, "wb") as f:
            pickle.dump(results, f)
    except Exception:
        pass


def load_results():
    if RESULTS_FILE.exists():
        try:
            with open(RESULTS_FILE, "rb") as f:
                data = pickle.load(f)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return []


# ============================================================
# 5. SESSION STATE
# ============================================================

if "fintech_results" not in st.session_state:
    st.session_state.fintech_results = load_results()

if "fintech_errors" not in st.session_state:
    st.session_state.fintech_errors = []


# ============================================================
# 6. SIDEBAR
# ============================================================

st.sidebar.markdown("## FinTech Research")
st.sidebar.caption("Bank annual report analysis")
st.sidebar.markdown("---")
st.sidebar.markdown("### Study Period")

from_year = st.sidebar.selectbox(
    "From financial year", FINANCIAL_YEARS,
    index=FINANCIAL_YEARS.index("2015-16"), key="study_from_year",
)
to_year = st.sidebar.selectbox(
    "To financial year", FINANCIAL_YEARS,
    index=FINANCIAL_YEARS.index("2024-25"), key="study_to_year",
)

study_period_valid = year_sort_key(from_year) <= year_sort_key(to_year)
if not study_period_valid:
    st.sidebar.error("The starting year must not be later than the ending year.")

st.sidebar.markdown("---")
st.sidebar.markdown("### Dashboard")

page = st.sidebar.radio(
    "Go to",
    ["Report Collection", "Overview", "Parameter Analysis",
     "Yearly Trends", "Bank Comparison", "Reports & Downloads"],
    label_visibility="collapsed",
)

st.sidebar.markdown("---")
st.sidebar.caption("Index scores are based on keyword detection in annual-report text.")

if st.sidebar.button("Clear all saved results"):
    st.session_state.fintech_results = []
    st.session_state.fintech_errors = []
    if RESULTS_FILE.exists():
        RESULTS_FILE.unlink()
    st.rerun()


# ============================================================
# 7. REPORT COLLECTION
# ============================================================

if page == "Report Collection":
    st.header("Report Collection")
    st.write(
        "Upload annual reports as PDF files or provide direct PDF links. "
        "The app tries to identify the bank and financial year from each "
        "filename. You can correct both before processing."
    )

    upload_tab, link_tab = st.tabs(["Upload PDF Reports", "Use PDF Links"])
    upload_records, link_records = [], []

    with upload_tab:
        uploaded_files = st.file_uploader(
            "Choose one or more bank annual-report PDFs",
            type=["pdf"], accept_multiple_files=True,
            key="annual_report_uploader",
        )

        if uploaded_files:
            st.markdown("#### Check the detected details")

            for uploaded_file in uploaded_files:
                # Key on file name + size so reordering uploads keeps typed edits.
                fid = f"{uploaded_file.name}_{uploaded_file.size}"
                detected_bank, detected_year = detect_bank_and_year(uploaded_file.name)

                with st.container(border=True):
                    st.markdown(f"**PDF:** `{uploaded_file.name}`")
                    c1, c2 = st.columns(2)

                    with c1:
                        bank = st.text_input(
                            "Bank name", value=detected_bank, key=f"bank_{fid}"
                        )
                    with c2:
                        options = ["— Select year —"] + FINANCIAL_YEARS
                        idx = options.index(detected_year) if detected_year in FINANCIAL_YEARS else 0
                        year = st.selectbox(
                            "Financial year", options, index=idx, key=f"year_{fid}"
                        )
                        if idx == 0 and year == "— Select year —":
                            st.caption("Year not detected. Please select it.")

                    upload_records.append({
                        "file": uploaded_file,
                        "bank": bank.strip(),
                        "year": "" if year == "— Select year —" else year,
                        "source": uploaded_file.name,
                    })

    with link_tab:
        st.markdown("Enter one report per line:")
        st.code(
            "Bank Name | Financial Year | Direct PDF URL\n"
            "Bank of Baroda | 2019-20 | https://example.com/report.pdf",
            language="text",
        )
        link_text = st.text_area(
            "Report links", height=180, key="pdf_link_text",
            placeholder="Bank of Baroda | 2019-20 | https://...",
        )

        if link_text.strip():
            for n, line in enumerate(link_text.splitlines(), start=1):
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = [p.strip() for p in line.split("|", 2)]
                if len(parts) != 3:
                    st.warning(f"Line {n} skipped. Use: Bank Name | Financial Year | Direct PDF URL")
                    continue

                bank, year, url = parts
                if year not in FINANCIAL_YEARS:
                    st.warning(f"Line {n}: '{year}' is not in the financial-year list.")
                    continue
                if not bank or not url:
                    st.warning(f"Line {n} needs a bank name and a URL.")
                    continue

                link_records.append({"bank": bank, "year": year, "url": url, "source": url})

    st.markdown("---")
    c1, c2 = st.columns([1, 2])

    with c1:
        process_button = st.button(
            "Analyse Reports", type="primary",
            use_container_width=True, disabled=not study_period_valid,
        )
    with c2:
        st.caption("Only reports within the selected study period are analysed.")

    if process_button:
        candidates = []

        for record in upload_records:
            if not record["bank"]:
                st.error(f"Please enter a bank name for {record['source']}.")
                continue
            if not record["year"]:
                st.error(f"Please select a financial year for {record['source']}.")
                continue
            candidates.append({**record, "kind": "upload"})

        for record in link_records:
            candidates.append({**record, "kind": "url"})

        study_set = set(get_study_years(from_year, to_year))
        to_process = [r for r in candidates if r["year"] in study_set]
        skipped = [r for r in candidates if r["year"] not in study_set]

        if skipped:
            st.warning(
                f"{len(skipped)} report(s) fall outside {from_year} to {to_year} "
                "and were skipped: "
                + "; ".join(f"{r['bank']} ({r['year']})" for r in skipped)
                + ". Change the study period in the sidebar to include them."
            )

        if not to_process:
            st.warning("No valid reports are ready to analyse. Check names, years and links.")
        else:
            existing = {
                (r["bank"].strip().lower(), r["year"]): r
                for r in st.session_state.fintech_results
            }

            new_results, new_errors, unchanged, overwritten = [], [], [], []
            progress = st.progress(0, text="Preparing reports...")

            for i, record in enumerate(to_process):
                try:
                    progress.progress(
                        int(i / len(to_process) * 100),
                        text=f"Analysing {record['bank']} ({record['year']})...",
                    )

                    pdf_bytes = (
                        record["file"].getvalue() if record["kind"] == "upload"
                        else get_pdf_bytes_from_url(record["url"])
                    )

                    key = (record["bank"].strip().lower(), record["year"])
                    file_hash = hashlib.sha256(pdf_bytes).hexdigest()

                    # Skip identical file already analysed for this bank-year.
                    if key in existing and existing[key].get("file_hash") == file_hash:
                        unchanged.append(f"{record['bank']} ({record['year']})")
                        continue

                    result = analyse_pdf(
                        pdf_bytes=pdf_bytes,
                        bank_name=record["bank"],
                        financial_year=record["year"],
                        source_name=record["source"],
                    )

                    if key in existing:
                        overwritten.append(f"{record['bank']} ({record['year']})")

                    new_results.append(result)

                except Exception as exc:
                    new_errors.append({
                        "Bank": record.get("bank", ""),
                        "Financial Year": record.get("year", ""),
                        "Source": record.get("source", ""),
                        "Error": str(exc),
                    })

            progress.progress(100, text="Analysis finished.")

            if new_results:
                for result in new_results:
                    existing[(result["bank"].strip().lower(), result["year"])] = result
                st.session_state.fintech_results = list(existing.values())
                save_results(st.session_state.fintech_results)

            st.session_state.fintech_errors = new_errors

            if new_results:
                st.success(
                    f"Analysed {len(new_results)} report(s). "
                    "Open Overview or another page from the sidebar."
                )
            if overwritten:
                st.warning(
                    "Replaced earlier results for: " + "; ".join(overwritten)
                    + ". If these are different report types (e.g. standalone "
                    "and consolidated), include that in the bank name to keep both."
                )
            if unchanged:
                st.info("Already analysed (identical file), skipped: " + "; ".join(unchanged))
            if new_errors:
                st.error(f"{len(new_errors)} report(s) could not be analysed.")
                show_table(pd.DataFrame(new_errors), height=220)

    st.markdown("---")
    st.subheader("Current analysis data")

    current = st.session_state.fintech_results

    if current:
        full_df = build_index_dataframe(current)
        filtered = (
            full_df[full_df["Financial Year"].isin(set(get_study_years(from_year, to_year)))]
            if study_period_valid else pd.DataFrame()
        )

        m1, m2, m3 = st.columns(3)
        m1.metric("Reports analysed", len(filtered))
        m2.metric("Banks covered", filtered["Bank"].nunique() if not filtered.empty else 0)
        m3.metric(
            "Average index",
            f"{filtered['Index Percentage (%)'].mean():.2f}%" if not filtered.empty else "0.00%",
        )
        show_table(filtered)
    else:
        st.info("No reports have been analysed yet.")


# ============================================================
# 8. FILTER DATA FOR DASHBOARD PAGES
# ============================================================

all_results = st.session_state.fintech_results
all_index_df = build_index_dataframe(all_results)

if study_period_valid and not all_index_df.empty:
    selected_years = set(get_study_years(from_year, to_year))
    index_df = all_index_df[all_index_df["Financial Year"].isin(selected_years)].copy()
    results = [r for r in all_results if r["year"] in selected_years]
else:
    index_df = pd.DataFrame()
    results = []


# ============================================================
# 9. OVERVIEW
# ============================================================

if page == "Overview":
    st.header("Overview")
    st.write("A summary of the keyword-based FinTech Adoption Index for the selected study period.")

    if index_df.empty:
        st.info("No reports are available for this period. Visit Report Collection first.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Reports analysed", len(index_df))
        c2.metric("Banks covered", index_df["Bank"].nunique())
        c3.metric("Average index", f"{index_df['Index Percentage (%)'].mean():.2f}%")
        c4.metric("Highest index", f"{index_df['Index Percentage (%)'].max():.2f}%")

        st.markdown("### Index by bank and financial year")
        chart_df = index_df.pivot_table(
            index="Financial Year", columns="Bank",
            values="Index Percentage (%)", aggfunc="mean",
        ).sort_index(key=lambda x: x.map(year_sort_key))
        st.line_chart(chart_df)

        st.markdown("### Report-level results")
        show_table(index_df)

        st.download_button(
            "Download overview data (CSV)", data=make_csv(index_df),
            file_name="fintech_index_overview.csv", mime="text/csv",
        )


# ============================================================
# 10. PARAMETER ANALYSIS
# ============================================================

elif page == "Parameter Analysis":
    st.header("Parameter Analysis")
    st.write(
        f"Compare the {MAX_SCORE} FinTech parameters and inspect their "
        "binary scores and keyword occurrences."
    )

    if not results:
        st.info("Analyse reports first to see parameter results.")
    else:
        detail_df = combine_detail_rows(results, "parameter_details")

        if not detail_df.empty:
            selected_parameter = st.selectbox("Parameter", PARAMETERS, key="selected_parameter")

            selected = detail_df[detail_df["Parameter"] == selected_parameter].copy()
            st.markdown(f"#### Results for {selected_parameter}")

            if not selected.empty:
                pivot = selected.pivot_table(
                    index="Financial Year", columns="Bank",
                    values="Score", aggfunc="max",
                ).sort_index(key=lambda x: x.map(year_sort_key))
                st.bar_chart(pivot)
                show_table(selected)

            st.markdown("### All parameter scores")
            matrix_rows = []
            for r in results:
                row = {"Bank": r["bank"], "Financial Year": r["year"]}
                row.update(r["scores"])
                matrix_rows.append(row)

            matrix_df = pd.DataFrame(matrix_rows)
            show_table(matrix_df)

            st.download_button(
                "Download parameter scores (CSV)", data=make_csv(matrix_df),
                file_name="fintech_parameter_scores.csv", mime="text/csv",
            )

            st.markdown("### Keyword occurrence details")
            show_table(detail_df)

            st.download_button(
                "Download keyword details (CSV)", data=make_csv(detail_df),
                file_name="fintech_keyword_details.csv", mime="text/csv",
            )


# ============================================================
# 11. YEARLY TRENDS
# ============================================================

elif page == "Yearly Trends":
    st.header("Yearly Trends")
    st.write("Review how the average index and parameter scores change across the selected years.")

    if index_df.empty:
        st.info("Analyse reports first to view yearly trends.")
    else:
        yearly = (
            index_df.groupby("Financial Year", as_index=False)
            .agg(
                Average_Index=("Index Percentage (%)", "mean"),
                Reports=("Bank", "count"),
                Banks=("Bank", "nunique"),
            )
            .sort_values("Financial Year", key=lambda x: x.map(year_sort_key))
        )

        st.markdown("### Average FinTech Adoption Index")
        st.line_chart(yearly.set_index("Financial Year")["Average_Index"])

        st.markdown("### Reports and bank coverage")
        st.bar_chart(yearly.set_index("Financial Year")[["Reports", "Banks"]])

        st.markdown("### Yearly summary")
        yearly_display = yearly.rename(columns={
            "Average_Index": "Average Index (%)",
            "Reports": "Reports Analysed",
            "Banks": "Banks Covered",
        })
        yearly_display["Average Index (%)"] = yearly_display["Average Index (%)"].round(2)
        show_table(yearly_display)

        parameter_rows = []
        for r in results:
            row = {"Financial Year": r["year"], "Bank": r["bank"]}
            row.update(r["scores"])
            parameter_rows.append(row)

        parameter_df = pd.DataFrame(parameter_rows)

        if not parameter_df.empty:
            parameter_yearly = (
                parameter_df.groupby("Financial Year")[PARAMETERS]
                .mean().mul(100).round(2)
                .sort_index(key=lambda x: x.map(year_sort_key))
            )

            st.markdown("### Parameter match rate by year (%)")
            st.line_chart(parameter_yearly)
            show_table(parameter_yearly.reset_index())

            st.download_button(
                "Download yearly trends (CSV)", data=make_csv(yearly_display),
                file_name="fintech_yearly_trends.csv", mime="text/csv",
            )
            st.download_button(
                "Download parameter trends (CSV)",
                data=make_csv(parameter_yearly.reset_index()),
                file_name="fintech_parameter_yearly_trends.csv", mime="text/csv",
            )


# ============================================================
# 12. BANK COMPARISON
# ============================================================

elif page == "Bank Comparison":
    st.header("Bank Comparison")
    st.write("Compare banks for a selected financial year using the overall index and parameter scores.")

    if index_df.empty:
        st.info("Analyse reports first to compare banks.")
    else:
        available_years = sorted(index_df["Financial Year"].dropna().unique(), key=year_sort_key)

        compare_year = st.selectbox(
            "Financial year to compare", available_years,
            index=len(available_years) - 1,
        )

        compare_df = (
            index_df[index_df["Financial Year"] == compare_year]
            .sort_values("Index Percentage (%)", ascending=False)
        )

        st.markdown(f"### Overall index: {compare_year}")
        st.bar_chart(compare_df[["Bank", "Index Percentage (%)"]].set_index("Bank"))

        show_table(compare_df[[
            "Bank", "Financial Year", "Overall Score",
            "Maximum Score", "Index Percentage (%)",
        ]])

        st.markdown("### Parameter comparison matrix")
        matrix = compare_df[["Bank"] + PARAMETERS].set_index("Bank")
        show_table(matrix.reset_index())

        st.download_button(
            "Download bank comparison (CSV)", data=make_csv(compare_df),
            file_name=f"bank_comparison_{compare_year}.csv", mime="text/csv",
        )
        st.download_button(
            "Download parameter matrix (CSV)", data=make_csv(matrix.reset_index()),
            file_name=f"bank_parameter_matrix_{compare_year}.csv", mime="text/csv",
        )


# ============================================================
# 13. REPORTS AND DOWNLOADS
# ============================================================

elif page == "Reports & Downloads":
    st.header("Reports & Downloads")
    st.write("Download the annual index matrix, parameter-level results, keyword evidence and processing errors.")

    if index_df.empty:
        st.info("Analyse reports first to generate downloadable results.")
    else:
        st.markdown("### Annual index matrix")
        matrix_columns = (
            ["Bank", "Financial Year"] + PARAMETERS
            + ["Overall Score", "Maximum Score", "Index Percentage (%)"]
        )
        matrix_df = index_df[[c for c in matrix_columns if c in index_df.columns]].copy()
        show_table(matrix_df)

        st.download_button(
            "Download annual index matrix (CSV)", data=make_csv(matrix_df),
            file_name="fintech_annual_index_matrix.csv", mime="text/csv",
            use_container_width=True,
        )

        st.markdown("### Report-level summary")
        summary_columns = [
            "Bank", "Financial Year", "Overall Score",
            "Maximum Score", "Index Percentage (%)", "Source",
        ]
        summary_df = index_df[[c for c in summary_columns if c in index_df.columns]].copy()
        show_table(summary_df, height=300)

        st.download_button(
            "Download report summary (CSV)", data=make_csv(summary_df),
            file_name="fintech_report_summary.csv", mime="text/csv",
            use_container_width=True,
        )

        st.markdown("### Parameter-level details")
        parameter_details = combine_detail_rows(results, "parameter_details")
        show_table(parameter_details)

        if not parameter_details.empty:
            st.download_button(
                "Download parameter details (CSV)", data=make_csv(parameter_details),
                file_name="fintech_parameter_details.csv", mime="text/csv",
                use_container_width=True,
            )

        st.markdown("### Keyword evidence")
        evidence_df = combine_detail_rows(results, "evidence_rows")
        show_table(evidence_df)

        if not evidence_df.empty:
            st.download_button(
                "Download evidence (CSV)", data=make_csv(evidence_df),
                file_name="fintech_keyword_evidence.csv", mime="text/csv",
                use_container_width=True,
            )

        st.markdown("### Processing errors")
        errors_df = pd.DataFrame(st.session_state.fintech_errors)

        if errors_df.empty:
            st.success("There are no recorded processing errors in the latest run.")
        else:
            show_table(errors_df)
            st.download_button(
                "Download processing errors (CSV)", data=make_csv(errors_df),
                file_name="fintech_processing_errors.csv", mime="text/csv",
                use_container_width=True,
            )


# ============================================================
# 14. FOOTER
# ============================================================

st.markdown("---")
st.caption(
    f"Methodology note: each of the {MAX_SCORE} parameters receives a binary score "
    "based on whether the report text contains at least one matching dictionary "
    "keyword. The index percentage is the total score divided by the number of "
    "parameters, multiplied by 100. Keyword presence measures disclosure in the "
    "report and does not independently confirm the bank's actual level of FinTech "
    "adoption. A score of zero means no matching keyword was detected in the "
    "extracted text; it does not necessarily mean the bank has not adopted that "
    "technology."
)
st.caption(
    "Technical note: scanned PDFs may require OCR, and links must point to "
    "accessible PDF files rather than pages that merely display a PDF."
)