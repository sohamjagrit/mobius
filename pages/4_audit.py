import streamlit as st

ss = st.session_state

st.title("Fabrication audit")
st.caption("Two layers: rapidfuzz string matching auto-passes bullets close to their source; "
           "low-similarity bullets escalate to Haiku for a semantic fabrication check. "
           "Verbatim bullets aren't audited — they're unchanged from your master.")

results = ss.get("audit")
if not ss.get("tailored"):
    st.info("Tailor a resume first.", icon=":material/auto_awesome:")
    st.page_link("pages/3_tailor.py", label="Go to tailoring", icon=":material/auto_awesome:")
    st.stop()

if not results:
    st.success("No rewritten or added bullets to audit — every bullet is verbatim from your master.",
               icon=":material/verified:")
    st.stop()

flagged = [r for r in results if not r.get("ok", True)]
passed = [r for r in results if r.get("ok", True)]

m1, m2, m3 = st.columns(3)
m1.metric("Checked", len(results), border=True)
m2.metric("Passed", len(passed), border=True)
m3.metric("Flagged", len(flagged), border=True)

if flagged:
    st.subheader("Flagged", divider="red")
    for r in flagged:
        layer = r.get("layer", "haiku")
        st.error(
            f"**{r.get('pair_id', '?')}**  ·  _{layer}_\n\n"
            f"Novel claims: {', '.join(r.get('novel_claims', [])) or '—'}",
            icon=":material/flag:",
        )

if passed:
    with st.expander(f"Passed ({len(passed)})", icon=":material/check_circle:"):
        for r in passed:
            layer = r.get("layer", "haiku")
            score = f" · {r['score']}% match" if "score" in r else ""
            st.markdown(f":green-badge[pass] `{r.get('pair_id', '?')}` — {layer}{score}")
