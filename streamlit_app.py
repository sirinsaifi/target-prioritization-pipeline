"""
Streamlit UI — thin client over the FastAPI backend.

Deliberately does no scoring/classification/gap logic itself and never
touches the database directly: it only calls the API endpoints and displays
what they return, so there is exactly one place (the FastAPI app) where the
deterministic modules run. Built last, per the project's build order (see
README.md / CLAUDE.md) — every number shown here was already computed and
verified end-to-end via the API before this UI existed.

Run:
    streamlit run streamlit_app.py
(with the FastAPI backend already running: uvicorn app.main:app --reload)

The API base URL defaults to localhost for local dev, but is overridable via
the API_BASE_URL env var — needed in Docker Compose, where the UI container
reaches the backend container by service name (e.g. "http://api:8000"),
not "localhost" (that would mean the UI container itself).
"""

import json
import os

import requests
import streamlit as st

st.set_page_config(page_title="ALS Target Prioritization", layout="wide")

DEFAULT_API_BASE = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_BASE = st.sidebar.text_input("API base URL", value=DEFAULT_API_BASE)

st.title("Evidence-Guided Target Prioritization & Research Gap Identification")
st.caption("Prototype scoped to Amyotrophic Lateral Sclerosis (Open Targets MONDO_0004976). "
           "Deterministic modules compute every number; this UI only displays them.")


def api_get(path: str):
    resp = requests.get(f"{API_BASE}{path}", timeout=30)
    if resp.status_code >= 400:
        return None, resp.json().get("detail", resp.text)
    return resp.json(), None


def api_post(path: str):
    resp = requests.post(f"{API_BASE}{path}", timeout=60)
    if resp.status_code >= 400:
        return None, resp.json().get("detail", resp.text)
    return resp.json(), None


targets, err = api_get("/targets/")
if err or not targets:
    st.warning("No targets found. Seed them first.")
    if st.button("Seed candidate targets"):
        _, seed_err = api_post("/targets/seed")
        if seed_err:
            st.error(seed_err)
        else:
            st.rerun()
    st.stop()

gene_by_symbol = {t["gene_symbol"]: t for t in targets}
gene_symbol = st.sidebar.selectbox("Candidate gene", sorted(gene_by_symbol))
target = gene_by_symbol[gene_symbol]
target_id = target["id"]

st.sidebar.markdown(f"**Ensembl ID:** `{target['ensembl_id']}`")
st.sidebar.markdown(f"**Disease EFO ID:** `{target['disease_efo_id']}`")

st.sidebar.divider()
st.sidebar.subheader("Pipeline steps")
st.sidebar.caption("Run in order: Scoring depends on Contradictions having "
                    "already logged for this target; Gaps depends on Scoring.")

if st.sidebar.button("1. Run contradiction check"):
    result, run_err = api_post(f"/contradictions/target/{target_id}/run")
    if run_err:
        st.sidebar.error(run_err)
    else:
        st.sidebar.success(f"{len(result)} contradiction(s) logged.")

if st.sidebar.button("2. Compute scores"):
    result, run_err = api_post(f"/scoring/target/{target_id}/compute")
    if run_err:
        st.sidebar.error(run_err)
    else:
        st.sidebar.success("Scores computed.")

if st.sidebar.button("3. Run gap analysis"):
    result, run_err = api_post(f"/gaps/target/{target_id}/run")
    if run_err:
        st.sidebar.error(run_err)
    else:
        st.sidebar.success(f"{len(result['gaps'])} gap(s) identified — {result['investigation_coverage']}.")

narrative_data, narr_err = api_get(f"/narrative/target/{target_id}")
if narr_err:
    st.error(narr_err)
    st.stop()

context = narrative_data["context"]

if not context["has_scores"]:
    st.info("No scores computed yet for this target — use the sidebar steps, then reload.")
    st.stop()

st.subheader(f"{gene_symbol} — Evidence Profile")
col1, col2, col3, col4 = st.columns(4)
col1.metric("Strength", f"{context['evidence_strength']:.2f}")
col2.metric("Consistency", f"{context['evidence_consistency']:.2f}")
col3.metric("Maturity", f"{context['evidence_maturity']:.2f}")
col4.metric("Composite priority", f"{context['priority_score']:.2f}")
st.caption("Strength / Consistency / Maturity are kept separate by design — the composite "
           "priority score is a simple average for ranking convenience only, not a new "
           "OTP-style association score.")

left, right = st.columns(2)

with left:
    st.markdown("**Per-dimension scores**")
    if context["dimension_breakdown"]:
        st.bar_chart(context["dimension_breakdown"])
    else:
        st.write("No dimension scores yet.")

    st.markdown("**Evidence record counts**")
    if context["evidence_record_counts"]:
        st.table(context["evidence_record_counts"])
    else:
        st.write("No evidence ingested for this target yet.")

with right:
    st.markdown("**Contradictions**")
    contra = context["contradictions"]
    if contra["total_logged"] == 0:
        st.write("None logged (either none found, or the classifier hasn't run for this target).")
    else:
        st.write(f"{contra['total_logged']} total, by classification:")
        st.table(contra["counts"])
        with st.expander("Example logged pairs"):
            st.json(contra["examples"])

    st.markdown("**Research gaps**")
    if context["gaps"]:
        for g in context["gaps"]:
            with st.expander(f"[{g['gap_type']}]"):
                st.write(g["rationale"])
                st.write(g["investigation_suggestion"])
    else:
        st.write("None identified (or gap analysis hasn't run for this target).")

st.divider()
st.subheader("Narrative")
st.text(narrative_data["narrative"])

with st.expander("Raw context (full traceability)"):
    st.json(context)
