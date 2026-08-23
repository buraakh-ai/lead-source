import csv
import io
import json
import os
from datetime import date
from typing import Any
from uuid import uuid4

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

US_STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut",
    "Delaware", "Florida", "Georgia", "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa",
    "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland", "Massachusetts", "Michigan",
    "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire",
    "New Jersey", "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio",
    "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina", "South Dakota",
    "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia",
    "Wisconsin", "Wyoming",
]

STATE_AREAS = {
    "California": ["Orange County", "Los Angeles County", "San Diego County", "Riverside County", "San Bernardino County", "Ventura County", "Irvine", "Tustin", "Anaheim", "Los Angeles", "San Diego"],
    "Texas": ["Austin", "Dallas", "Fort Worth", "Houston", "San Antonio"],
    "Florida": ["Miami", "Orlando", "Tampa", "Jacksonville", "Fort Lauderdale"],
    "New York": ["New York City", "Buffalo", "Rochester", "Albany", "Syracuse"],
    "Illinois": ["Chicago", "Springfield", "Naperville", "Rockford", "Peoria"],
}

INDUSTRY_SUGGESTIONS = [
    "Restaurants", "Retail", "Dentists", "Beauty salons and spas", "Gyms and fitness",
    "Medical clinics", "Real estate", "Construction", "Professional services", "Automotive",
]

ROLE_SUGGESTIONS = ["Owner", "Founder", "General Manager", "Finance Manager", "Practice Manager", "Operations Manager"]

st.set_page_config(page_title="Lead Sourcing | Public-Source MVP", page_icon="🔎", layout="wide")
st.title("Lead Sourcing")
st.caption("Module 1 · Discover, enrich, verify and centralize public business prospects for downstream Ad Generator campaigns.")

for key, default in {
    "campaign_id": str(uuid4()),
    "lead_sources": [],
    "leads": [],
    "run_summary": None,
    "loaded_campaign": {},
}.items():
    st.session_state.setdefault(key, default)


def _split_csv(value: str) -> list[str]:
    return list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))


def _post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    response = requests.post(f"{BACKEND_URL}{path}", json=payload, timeout=1200)
    if not response.ok:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise RuntimeError(f"{response.status_code}: {detail}")
    return response.json()


def _database_status() -> bool:
    try:
        response = requests.get(f"{BACKEND_URL}/health", timeout=10)
        response.raise_for_status()
        return bool(response.json().get("database_configured"))
    except requests.RequestException:
        return False


def _csv_bytes(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b""
    fieldnames = list(dict.fromkeys(key for row in rows for key in row))
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: " | ".join(value) if isinstance(value, list) else value for key, value in row.items()})
    return output.getvalue().encode("utf-8-sig")


loaded = st.session_state.loaded_campaign

with st.sidebar:
    st.header("Sourcing campaign")
    uploaded = st.file_uploader("Load campaign JSON", type=["json"])
    if uploaded is not None and st.button("Apply uploaded campaign"):
        try:
            st.session_state.loaded_campaign = json.load(uploaded)
            st.session_state.campaign_id = st.session_state.loaded_campaign.get("campaign_id", str(uuid4()))
            st.rerun()
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            st.error(f"Invalid campaign file: {exc}")

    campaign_name = st.text_input("Campaign name", value=loaded.get("campaign_name", "California Small Business Discovery"))
    campaign_status = st.selectbox("Status", ["draft", "active", "paused", "completed"], index=1)
    date_col1, date_col2 = st.columns(2)
    period_start = date_col1.date_input("Start", value=date.fromisoformat(loaded.get("period_start", date.today().isoformat())))
    period_end = date_col2.date_input("End", value=date.fromisoformat(loaded.get("period_end", date.today().isoformat())))

    st.subheader("Dynamic geography")
    country = st.selectbox("Country", ["United States", "Canada", "United Kingdom", "Australia", "Other"], index=0)
    if country == "United States":
        default_state = loaded.get("state", "California")
        state_index = US_STATES.index(default_state) if default_state in US_STATES else US_STATES.index("California")
        state = st.selectbox("State", US_STATES, index=state_index)
    else:
        state = st.text_input("State / province / region", value=loaded.get("state", ""))
    suggested_areas = STATE_AREAS.get(state, [])
    selected_areas = st.multiselect("Suggested counties or cities", suggested_areas)
    custom_areas = st.text_input("Additional cities, counties or ZIP codes", value=", ".join(loaded.get("cities_or_areas", [])), placeholder="Irvine, Tustin, 92780")

    st.subheader("Business targeting")
    selected_industries = st.multiselect("Industries", INDUSTRY_SUGGESTIONS, default=loaded.get("industries", ["Restaurants", "Retail"]))
    custom_industries = st.text_input("Additional industries", placeholder="Accountants, hotels, manufacturers")
    subcategories_text = st.text_input("Subcategories", value=", ".join(loaded.get("subcategories", [])), placeholder="Independent restaurants, specialty retailers")
    selected_roles = st.multiselect("Decision-maker roles", ROLE_SUGGESTIONS, default=loaded.get("decision_maker_roles", ROLE_SUGGESTIONS[:4]))
    custom_roles = st.text_input("Additional roles", placeholder="Managing Partner, Controller")
    inclusion_text = st.text_input("Include keywords", value=", ".join(loaded.get("inclusion_keywords", [])), placeholder="independent, locally owned")
    exclusion_text = st.text_input("Exclude keywords", value=", ".join(loaded.get("exclusion_keywords", [])), placeholder="permanently closed, franchise corporate office")

    st.subheader("Run controls")
    source_count = st.slider("Businesses to discover", 1, 50, 10)
    lead_count = st.slider("Qualified leads to return", 1, 50, 10)
    persist_to_database = st.checkbox("Push results to AWS PostgreSQL", value=True)

areas = list(dict.fromkeys(selected_areas + _split_csv(custom_areas)))
industries = list(dict.fromkeys(selected_industries + _split_csv(custom_industries)))
roles = list(dict.fromkeys(selected_roles + _split_csv(custom_roles)))
campaign = {
    "campaign_id": st.session_state.campaign_id,
    "campaign_name": campaign_name,
    "campaign_status": campaign_status,
    "period_start": period_start.isoformat(),
    "period_end": period_end.isoformat(),
    "country": country,
    "state": state,
    "geography": ", ".join(areas + [state, country]),
    "cities_or_areas": areas,
    "industries": industries,
    "subcategories": _split_csv(subcategories_text),
    "decision_maker_roles": roles,
    "inclusion_keywords": _split_csv(inclusion_text),
    "exclusion_keywords": _split_csv(exclusion_text),
}

top1, top2, top3, top4 = st.columns([1.2, 1, 1, 2])
run_campaign = top1.button("Run lead sourcing", type="primary", use_container_width=True, disabled=not industries or period_end < period_start)
if top2.button("New campaign", use_container_width=True):
    st.session_state.campaign_id = str(uuid4())
    st.session_state.lead_sources = []
    st.session_state.leads = []
    st.session_state.run_summary = None
    st.session_state.loaded_campaign = {}
    st.rerun()
top3.download_button("Save campaign JSON", data=json.dumps(campaign, indent=2), file_name=f"{campaign_name.lower().replace(' ', '_')}.json", mime="application/json", use_container_width=True)
db_ready = _database_status()
top4.write(f"**Destination:** {'AWS PostgreSQL configured' if db_ready else 'CSV available · AWS PostgreSQL not configured'} → Ad Generator")

if run_campaign:
    progress = st.progress(10, text="Starting public-source discovery…")
    try:
        result = _post("/run-sourcing-campaign", {"campaign": campaign, "source_count": source_count, "lead_count": lead_count, "persist_to_database": persist_to_database})
        progress.progress(100, text="Lead sourcing completed")
        st.session_state.lead_sources = result["lead_sources"]
        st.session_state.leads = result["leads"]
        st.session_state.run_summary = result["run_summary"]
        st.success("Sourcing run completed.")
    except (requests.RequestException, RuntimeError) as exc:
        progress.empty()
        st.error(f"Sourcing run failed: {exc}")

campaign_tab, sources_tab, leads_tab, handoff_tab = st.tabs(["1 · Campaign", "2 · Source discovery", "3 · Qualified leads", "4 · Database handoff"])

with campaign_tab:
    st.subheader(campaign_name)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Period", f"{period_start:%b %d} – {period_end:%b %d}")
    c2.metric("State / region", state or "—")
    c3.metric("Target locations", len(areas))
    c4.metric("Industries", len(industries))
    st.json(campaign, expanded=False)

with sources_tab:
    sources = st.session_state.lead_sources
    if sources:
        c1, c2, c3 = st.columns(3)
        c1.metric("Sources discovered", len(sources))
        c2.metric("Verified", sum(source.get("verification_status") == "verified" for source in sources))
        c3.metric("With phone", sum(bool(source.get("public_phone")) for source in sources))
        st.dataframe(sources, use_container_width=True, hide_index=True)
    else:
        st.info("Run the campaign to discover public business sources.")

with leads_tab:
    leads = st.session_state.leads
    if leads:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Leads returned", len(leads))
        c2.metric("Business emails", sum(bool(lead.get("business_email")) for lead in leads))
        c3.metric("Decision makers", sum(bool(lead.get("decision_maker_name")) for lead in leads))
        c4.metric("Verified", sum(lead.get("verification_status") == "verified" for lead in leads))
        columns = ["business_name", "category", "city", "state", "phone", "business_email", "decision_maker_name", "decision_maker_role", "verification_status", "lead_score"]
        st.dataframe([{key: lead.get(key) for key in columns} for lead in leads], use_container_width=True, hide_index=True)
        st.download_button("Download leads CSV", data=_csv_bytes(leads), file_name=f"{campaign_name.lower().replace(' ', '_')}_leads.csv", mime="text/csv", type="primary")
        with st.expander("Lead evidence and marketing context"):
            for lead in leads:
                st.markdown(f"**{lead.get('business_name') or lead.get('name')}** — {lead.get('marketing_notes') or 'No marketing note generated.'}")
                for evidence_url in lead.get("source_urls") or []:
                    st.markdown(f"- [{evidence_url}]({evidence_url})")
    else:
        st.info("Qualified leads will appear after a sourcing run.")

with handoff_tab:
    summary = st.session_state.run_summary
    if summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Run ID", summary["run_id"][:8])
        c2.metric("Duration", f"{summary['duration_seconds']:.1f}s")
        c3.metric("Sources", summary["sources_discovered"])
        c4.metric("Leads", summary["leads_returned"])
        if summary["database_saved"]:
            st.success(summary["database_message"])
        else:
            st.warning(summary["database_message"])
        st.json(summary, expanded=False)
    else:
        st.info("The run summary and AWS PostgreSQL handoff status will appear here.")
