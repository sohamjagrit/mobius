import json

import streamlit as st

import app_common as ac
import config

profile = st.session_state.get("profile")
if not profile:
    st.warning("Upload a resume first.", icon=":material/upload_file:")
    st.page_link("pages/1_onboarding.py", label="Go to onboarding", icon=":material/upload_file:")
    st.stop()

st.title("Page-fit selection")
budget = ac.page_fit_selection(profile)

if st.button("Save settings & start tailoring", type="primary",
             icon=":material/rocket_launch:", use_container_width=True):
    config.settings_path(st.session_state.profile_hash).write_text(json.dumps(budget, indent=2), encoding="utf-8")
    config.LAST_FILE.write_text(st.session_state.profile_hash, encoding="utf-8")
    st.session_state.budget = budget
    st.switch_page("pages/3_tailor.py")
