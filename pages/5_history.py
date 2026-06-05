import streamlit as st

from services import history

ss = st.session_state

st.title("History")
st.caption("Every tailored resume is saved with its job description. Reload one to view or re-edit it.")

runs = history.list_runs()
if not runs:
    st.info("No tailored resumes yet.", icon=":material/history:")
    st.stop()

for run in runs:
    with st.container(border=True):
        c1, c2 = st.columns([4, 1])
        with c1:
            st.markdown(f"**{run.get('role') or run.get('slug') or run['name']}**")
            bits = [run.get("date", "")]
            if run.get("flagged"):
                bits.append(f"{run['flagged']} flagged")
            if run.get("cost"):
                bits.append(f"${run['cost']:.4f}")
            st.caption("  ·  ".join(b for b in bits if b))
        if c2.button("Reload", key=f"reload_{run['name']}", icon=":material/open_in_new:",
                     use_container_width=True):
            loaded = history.load_run(run["run_id"])
            for k in list(ss.keys()):
                if k.startswith("ed_"):
                    ss.pop(k, None)
            ss.keywords = []
            ss.update(loaded)
            st.switch_page("pages/3_tailor.py")
