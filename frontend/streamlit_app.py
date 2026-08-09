import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

st.set_page_config(page_title="AI Lead Generation", page_icon="📇", layout="centered")
st.title("AI Lead Generation Pipeline")
st.caption(
    "Runs the three-stage Agno pipeline (Business Research → Lead Source Research → "
    "Lead Puller) against the FastAPI backend."
)

for key in ("business_research", "lead_sources", "leads"):
    st.session_state.setdefault(key, None)


def _post(path: str, json: dict) -> dict:
    resp = requests.post(f"{BACKEND_URL}{path}", json=json, timeout=300)
    resp.raise_for_status()
    return resp.json()


url = st.text_input("Business website URL", placeholder="https://example.com")
col1, col2 = st.columns(2)
source_count = col1.number_input("Lead sources to find", min_value=1, max_value=8, value=3)
lead_count = col2.number_input("Leads to pull", min_value=1, max_value=8, value=3)

st.divider()

# --- Stage 1: Business research -------------------------------------------------
st.subheader("1. Research business")
if st.button("Run business research", disabled=not url.strip()):
    with st.spinner("Researching business..."):
        try:
            st.session_state.business_research = _post("/research-business", {"url": url})
            st.session_state.lead_sources = None
            st.session_state.leads = None
        except requests.RequestException as exc:
            st.error(f"Business research failed: {exc}")

if st.session_state.business_research:
    st.json(st.session_state.business_research)

# --- Stage 2: Lead sources -------------------------------------------------------
st.subheader("2. Find lead sources")
if st.button("Find lead sources", disabled=not st.session_state.business_research):
    with st.spinner("Finding lead sources..."):
        try:
            payload = {
                "business_research": st.session_state.business_research,
                "source_count": int(source_count),
            }
            result = _post("/find-lead-sources", payload)
            st.session_state.lead_sources = result["lead_sources"]
            st.session_state.leads = None
        except requests.RequestException as exc:
            st.error(f"Lead source research failed: {exc}")

if st.session_state.lead_sources:
    st.json(st.session_state.lead_sources)

# --- Stage 3: Pull leads -------------------------------------------------------
st.subheader("3. Pull leads")
if st.button("Pull leads", disabled=not st.session_state.lead_sources):
    with st.spinner("Pulling leads..."):
        try:
            payload = {
                "lead_sources": st.session_state.lead_sources,
                "lead_count": int(lead_count),
            }
            result = _post("/pull-leads", payload)
            st.session_state.leads = result["leads"]
        except requests.RequestException as exc:
            st.error(f"Lead pulling failed: {exc}")

if st.session_state.leads:
    st.dataframe(st.session_state.leads, use_container_width=True)

st.divider()

# --- Convenience: run everything in one call ------------------------------------
st.subheader("Or run the whole pipeline at once")
if st.button("Run full pipeline", disabled=not url.strip(), type="primary"):
    with st.spinner("Running full pipeline (this can take a few minutes)..."):
        try:
            payload = {"url": url, "source_count": int(source_count), "lead_count": int(lead_count)}
            result = _post("/run-pipeline", payload)
            st.session_state.business_research = result["business_research"]
            st.session_state.lead_sources = result["lead_sources"]
            st.session_state.leads = result["leads"]
            st.success("Pipeline complete.")
        except requests.RequestException as exc:
            st.error(f"Pipeline run failed: {exc}")
