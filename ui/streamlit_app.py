"""
Streamlit UI — GCP Document Intelligence System

Shows:
- Run HN or upload a PDF
- Pick Flash/Pro
- View summaries + sentiment + entities + PII (uploads)
- View basic aggregate stats
- Top N entities control inside Entities tab (default 5)
- "Select a document" ONLY for Hacker News
- Refresh button to avoid cached empty results
"""

import os
import time
import json
from typing import Any, Dict, List, Optional

import pandas as pd
import requests
import streamlit as st

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────
DEFAULT_API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

st.set_page_config(page_title="GCP Document Intelligence System", layout="wide")
st.title("🧠 GCP Document Intelligence System")
st.caption("Entities | Sentiment | Key Info JSON | Summary | PII")


# ──────────────────────────────────────────────
# Sidebar
# ──────────────────────────────────────────────
with st.sidebar:
    st.header("Run Configuration")
    api_base_url = st.text_input("API Base URL", value=DEFAULT_API_BASE_URL)
    source = st.radio("Select Source", ["Hacker News", "Upload PDF"])
    uploaded_file = st.file_uploader("PDF", type=["pdf"]) if source == "Upload PDF" else None
    model = st.selectbox("Gemini Model Tier", ["flash", "pro"], index=0)
    run_button = st.button("Run Processing")


# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────
st.session_state.setdefault("last_run_id", None)
st.session_state.setdefault("last_source", None)
st.session_state.setdefault("refresh_token", 0)
st.session_state.setdefault("top_n_entities", 5)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────
def api_url(path: str) -> str:
    return api_base_url.rstrip("/") + path


def safe_json(resp: requests.Response) -> Dict[str, Any]:
    """Always return a dict regardless of backend response shape."""
    try:
        data = resp.json()
    except Exception:
        return {"message": f"Non-JSON response ({resp.status_code})", "raw": resp.text}
    if isinstance(data, dict):
        return data
    return {"message": f"Unexpected JSON type: {type(data).__name__}", "raw": data}


def show_error(response: requests.Response) -> None:
    data = safe_json(response)
    st.error(data.get("message") or data.get("detail") or "Request failed")
    with st.expander("Error Details"):
        st.code(json.dumps(data, indent=2, default=str))


def poll_until_complete(run_id: str, timeout_seconds: int = 900) -> Dict[str, Any]:
    start = time.time()
    while time.time() - start < timeout_seconds:
        r = requests.get(api_url(f"/run/{run_id}/status"))
        if not r.ok:
            show_error(r)
            return {"status": "FAILED"}
        status_data = safe_json(r)
        if status_data.get("status") in ["SUCCEEDED", "FAILED"]:
            return status_data
        time.sleep(2)
    return {"status": "FAILED", "error_message": "Timeout exceeded."}


def sentiment_label(score: Optional[float]) -> str:
    if score is None:
        return "unknown"
    if score > 0.05:
        return "positive"
    if score < -0.05:
        return "negative"
    return "neutral"


def entities_df(entities: List[Dict[str, Any]]) -> pd.DataFrame:
    if not entities:
        return pd.DataFrame(columns=["name", "type", "salience", "mentions"])
    df = pd.DataFrame(entities)
    for col in ["salience", "mentions"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["name", "type", "salience", "mentions"]:
        if col not in df.columns:
            df[col] = None
    return df


def pii_df(pii_findings: Dict[str, Any]) -> pd.DataFrame:
    findings = (pii_findings or {}).get("findings", [])
    if not findings:
        return pd.DataFrame(columns=["info_type", "likelihood", "quote"])
    return pd.DataFrame(findings)


@st.cache_data(show_spinner=False, ttl=10)
def get_run_results(api_base_url_: str, run_id: str, refresh_token: int) -> Dict[str, Any]:
    r = requests.get(api_base_url_.rstrip("/") + f"/run/{run_id}/results")
    r.raise_for_status()
    return r.json()


@st.cache_data(show_spinner=False, ttl=10)
def get_run_aggregate(api_base_url_: str, run_id: str, doc_id: Optional[str], refresh_token: int) -> Dict[str, Any]:
    params = {"doc_id": doc_id} if doc_id else {}
    r = requests.get(api_base_url_.rstrip("/") + f"/run/{run_id}/aggregate", params=params)
    r.raise_for_status()
    return r.json()


# ──────────────────────────────────────────────
# Run Processing
# ──────────────────────────────────────────────
if run_button:
    st.session_state["last_source"] = source

    if source == "Hacker News":
        with st.spinner("Starting Hacker News run..."):
            resp = requests.post(api_url("/run/hn"), json={"model": model})
        if not resp.ok:
            show_error(resp)
            st.stop()

        run_id = resp.json().get("run_id")
        if not run_id:
            st.error("Backend did not return run_id.")
            st.stop()

        with st.spinner("Processing documents..."):
            status = poll_until_complete(run_id)

    else:
        if uploaded_file is None:
            st.warning("Upload a PDF in the sidebar.")
            st.stop()

        with st.spinner("Uploading and processing PDF..."):
            files = {"file": (uploaded_file.name, uploaded_file.getvalue(), "application/pdf")}
            try:
                resp = requests.post(api_url(f"/upload/pdf?model={model}"), files=files, timeout=60)
            except requests.exceptions.RequestException as e:
                st.error("Can't reach the API. Is FastAPI running?")
                st.code(str(e))
                st.stop()

        if not resp.ok:
            show_error(resp)
            st.stop()

        run_id = resp.json().get("run_id")
        if not run_id:
            st.error("Backend did not return run_id.")
            st.stop()

        with st.spinner("Processing document..."):
            status = poll_until_complete(run_id)

    if status.get("status") == "FAILED":
        st.error(status.get("error_message", "Run failed."))
        st.stop()

    st.session_state["last_run_id"] = run_id
    st.session_state["refresh_token"] += 1


# ──────────────────────────────────────────────
# Display Results
# ──────────────────────────────────────────────
run_id = st.session_state.get("last_run_id")
last_source = st.session_state.get("last_source") or source

if not run_id:
    st.stop()

st.divider()

_, col_refresh = st.columns([3, 1])
with col_refresh:
    if st.button("🔄 Refresh"):
        st.session_state["refresh_token"] += 1

refresh_token = st.session_state["refresh_token"]

# Load results
try:
    results_payload = get_run_results(api_base_url, run_id, refresh_token)
    items = results_payload.get("items", [])
except requests.HTTPError as e:
    st.error("Failed to load results")
    st.code(str(e))
    st.stop()

if not items:
    st.info("No results yet — this can happen briefly right after a run completes. Hit Refresh.")
    st.stop()

# Document selector (HN only)
if last_source == "Hacker News":
    st.markdown("### Choose a news article")
    labels = [f"{i+1}. {(it.get('title') or '(Untitled)')[:80]}" for i, it in enumerate(items)]
    idx = st.selectbox("", list(range(len(items))), format_func=lambda i: labels[i], label_visibility="collapsed")
    item = items[idx]
else:
    item = items[0]

doc_id = item.get("doc_id")

# Aggregate metrics
try:
    agg = get_run_aggregate(api_base_url, run_id, doc_id, refresh_token)
    c1, c2 = st.columns(2)
    c1.metric("Articles", agg.get("docs", agg.get("docs_processed", "-")))
    c2.metric("Run status", agg.get("status", "-"))
except Exception:
    st.caption("Aggregate unavailable.")

# Summary
st.markdown("### Summary")
st.write(item.get("summary") or "")

# Sentiment
st.markdown("### Sentiment")
score = item.get("sentiment_score")
label = sentiment_label(score if isinstance(score, (int, float)) else None)
st.write(label)

if isinstance(score, (int, float)):
    st.markdown(
        f"""
        <div style="
            display:inline-block;
            padding:6px 14px;
            border-radius:20px;
            background-color:#153f2f;
            color:#6EE7B7;
            font-weight:500;
            font-size:16px;
        ">
            ↑ score={float(score):.3f}
        </div>
        """,
        unsafe_allow_html=True,
    )

# Insights tabs
st.markdown("### Insights")
tab_entities, tab_json, tab_pii, tab_baselines = st.tabs(["Entities", "Key Info JSON", "PII", "Baselines"])

with tab_entities:
    st.session_state["top_n_entities"] = st.number_input(
        "Top N Entities to show",
        min_value=1,
        max_value=50,
        value=int(st.session_state["top_n_entities"]),
        step=1,
    )
    top_n = int(st.session_state["top_n_entities"])
    df = entities_df(item.get("entities", []))

    if df.empty:
        st.info("No entities.")
    else:
        df["salience"] = pd.to_numeric(df.get("salience"), errors="coerce").fillna(0.0)
        df["mentions"] = pd.to_numeric(df.get("mentions"), errors="coerce").fillna(0.0)
        top = df.sort_values(by=["salience", "mentions"], ascending=False).head(top_n).copy()
        st.write("**Top entities:** " + ", ".join(str(x) for x in top["name"].fillna("").tolist() if str(x).strip()))
        st.dataframe(top[["name", "type", "mentions"]].rename(columns={"name": "entity"}), use_container_width=True)

with tab_json:
    st.json(item.get("extraction", {}))

with tab_pii:
    findings = pii_df(item.get("pii_findings", {}))
    if findings.empty:
        st.info("No PII findings (or not a user upload).")
    else:
        st.warning("PII detected. Quotes are truncated.")
        st.dataframe(findings, use_container_width=True)

with tab_baselines:
    st.info("Baseline comparison coming soon.")

# Full aggregate JSON expander
st.markdown("### Full Aggregate JSON")
st.caption("Complete structured output returned by the processing pipeline.")
with st.expander("View Full JSON Output", expanded=False):
    try:
        st.json(agg)
    except Exception:
        st.caption("Aggregate analytics unavailable.")
