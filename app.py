"""Mobius — resume tailoring app (multipage entrypoint).

Run with: uv run streamlit run app.py

Pages live in pages/; shared logic in app_common.py; backend in services/.
User data is stored under profiles/ and tailored/ in the repo (gitignored — see config.py).
Navigation is gated on setup state: onboarding is always available; configure
unlocks once a resume is loaded; tailor/audit/history unlock once settings are saved.
"""
import streamlit as st

import app_common as ac

st.set_page_config(page_title="Mobius", page_icon=":material/contrast:", layout="wide")
ac.bootstrap()

onboarding = st.Page("pages/1_onboarding.py", title="Onboarding", icon=":material/upload_file:")
configure  = st.Page("pages/2_configure.py", title="Configure",  icon=":material/tune:")
tailor     = st.Page("pages/3_tailor.py",    title="Tailor",     icon=":material/auto_awesome:")
tracker_pg = st.Page("pages/5_history.py",   title="Job Tracker",icon=":material/assignment:")

if ac.has_settings():
    pages = [tailor, tracker_pg, configure, onboarding]
elif ac.has_profile():
    pages = [configure, onboarding]
else:
    pages = [onboarding]

ac.sidebar_summary()
st.navigation(pages).run()
