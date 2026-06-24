import streamlit as st

from services import history, tracker

ss = st.session_state

st.set_page_config(page_title="Job Tracker", layout="wide")

col1, col2 = st.columns([0.7, 0.3])
with col1:
    st.title("Job Tracker")
with col2:
    st.caption("")

apps = tracker.load_applications()
runs = history.list_runs()

if not apps and not runs:
    st.info("No tracked applications or tailored resumes yet. Tailor a resume on the Tailor page.",
            icon=":material/assignment:")
    st.stop()

status_colors = {
    "Applied": "blue",
    "Pending": "orange",
    "Interviewing": "purple",
    "Rejected": "red",
    "Offer": "green",
}

tab_apps, tab_resumes = st.tabs(["Applications", "Tailored Resumes"])

with tab_apps:
    if not apps:
        st.info("No applications tracked yet.")
    else:
        st.caption(f"Total applications: {len(apps)}")

        for i, app in enumerate(reversed(apps)):
            with st.container(border=True):
                header_col1, header_col2, header_col3, header_col4 = st.columns([2.5, 1.2, 1, 0.8])

                with header_col1:
                    st.markdown(f"**{app['company']}**")
                    st.markdown(f"_{app['role']}_")

                with header_col2:
                    color = status_colors.get(app["status"], "gray")
                    st.markdown(f":{color}-badge[{app['status']}]")

                with header_col3:
                    st.caption(f"Applied: {app['date_applied']}")

                with header_col4:
                    if st.button("Edit", key=f"edit_{app['id']}", use_container_width=True):
                        ss.edit_app_id = app["id"]
                        st.rerun()

                if app.get("notes"):
                    st.divider()
                    st.caption(f"**Notes:** {app['notes']}")

                st.caption(f"Resume: `{app['resume_slug']}`")

                if ss.get("edit_app_id") == app["id"]:
                    st.divider()
                    col1, col2 = st.columns(2)

                    with col1:
                        new_status = st.selectbox(
                            "Update status",
                            ["Applied", "Pending", "Interviewing", "Rejected", "Offer"],
                            index=["Applied", "Pending", "Interviewing", "Rejected", "Offer"].index(app["status"]),
                            key=f"status_{app['id']}"
                        )

                    with col2:
                        st.empty()

                    new_notes = st.text_area(
                        "Notes",
                        value=app.get("notes", ""),
                        key=f"notes_{app['id']}",
                        height=80,
                        label_visibility="collapsed"
                    )

                    save_col, cancel_col, reload_col = st.columns(3)

                    with save_col:
                        if st.button("Save changes", key=f"save_{app['id']}", use_container_width=True):
                            tracker.update_application(app["id"], new_status, new_notes)
                            ss.pop("edit_app_id", None)
                            st.rerun()

                    with cancel_col:
                        if st.button("Cancel", key=f"cancel_{app['id']}", use_container_width=True):
                            ss.pop("edit_app_id", None)
                            st.rerun()

                    with reload_col:
                        if st.button("Reload resume", key=f"reload_{app['id']}", use_container_width=True):
                            loaded = history.load_run_by_slug(app["resume_slug"])
                            if loaded:
                                for k in list(ss.keys()):
                                    if k.startswith("ed_") or k.startswith("app_"):
                                        ss.pop(k, None)
                                ss.keywords = []
                                ss.update(loaded)
                                st.switch_page("pages/3_tailor.py")
                            else:
                                st.error("Resume not found.")

with tab_resumes:
    if not runs:
        st.info("No tailored resumes yet.")
    else:
        st.caption(f"Total tailored resumes: {len(runs)}")

        for run in runs:
            with st.container(border=True):
                col1, col2, col3, col4 = st.columns([2.5, 1, 1, 0.8])

                with col1:
                    st.markdown(f"**{run.get('slug') or run['name']}**")
                    st.markdown(f"_{run.get('role', 'No role')}_")
                    if run.get("role_resume"):
                        st.caption(f":material/badge: {run['role_resume']} resume")

                with col2:
                    st.caption(f"Date: {run.get('date', 'N/A')}")

                with col3:
                    if run.get('cost'):
                        st.caption(f"Cost: ${run['cost']:.4f}")

                with col4:
                    if st.button("Reload", key=f"reload_{run['name']}", use_container_width=True):
                        loaded = history.load_run(run["run_id"])
                        for k in list(ss.keys()):
                            if k.startswith("ed_"):
                                ss.pop(k, None)
                        ss.keywords = []
                        ss.update(loaded)
                        st.switch_page("pages/3_tailor.py")
