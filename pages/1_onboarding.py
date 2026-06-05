import streamlit as st

import app_common as ac

st.title("Master resume")
st.caption("Upload once. Fix anything the parser got wrong, then save. This is the source of truth for every tailored resume.")

uploaded = st.file_uploader("Upload your master resume (PDF or DOCX)", type=["pdf", "docx"])
if uploaded is not None:
    ac.load_master(uploaded.getvalue(), uploaded.name)

profile = st.session_state.get("profile")
if not profile:
    st.info("Upload a PDF or DOCX to begin.", icon=":material/upload_file:")
    st.stop()

st.subheader("Review & edit", divider="gray")
ac.profile_editor(profile)

st.divider()
if ac.valid_settings(st.session_state.get("budget")):
    st.page_link("pages/3_tailor.py", label="Start tailoring", icon=":material/auto_awesome:")
else:
    st.page_link("pages/2_configure.py", label="Next: configure page fit", icon=":material/tune:")
