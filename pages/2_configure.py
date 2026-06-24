import streamlit as st

import app_common as ac
from services import roles

profile = st.session_state.get("profile")
if not profile:
    st.warning("Upload a resume first.", icon=":material/upload_file:")
    st.page_link("pages/1_onboarding.py", label="Go to onboarding", icon=":material/upload_file:")
    st.stop()

st.title("Page-fit selection")
st.caption("One shared budget for every role resume. Set it against whichever resume is active; "
           "it applies to all of them.")
budget = ac.page_fit_selection(profile)

if st.button("Save settings & start tailoring", type="primary",
             icon=":material/rocket_launch:", use_container_width=True):
    roles.save_settings(budget)
    st.session_state.budget = budget
    st.switch_page("pages/3_tailor.py")
