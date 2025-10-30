import streamlit as st
import requests
from streamlit.components.v1 import html as components_html


st.set_page_config(page_title="Codebase Genius", layout="wide")


BASE_URL = "http://localhost:8000"
GENIUS_ENDPOINT = f"{BASE_URL}/walker/codebase_genius"
GET_ART_ENDPOINT = f"{BASE_URL}/walker/get_last_artifact"


st.title("🧠 Codebase Genius – Auto Docs from GitHub")


with st.sidebar:
  st.header("Generate Docs")
  repo_url = st.text_input("GitHub Repo URL", placeholder="https://github.com/owner/repo")
  run_btn = st.button("Run Pipeline ⚙️")
  st.markdown("---")
  sel_repo = st.text_input("Preview by Repo Name (optional)")
  load_btn = st.button("Load Last Artifact")


if run_btn and repo_url:
  with st.spinner("Running Codebase Genius..."):
    res = requests.post(GENIUS_ENDPOINT, json={"utterance": repo_url, "session_id": ""})
    if res.status_code == 200:
      reports = res.json().get("reports", [])
      msg = reports[0]["response"] if reports else "No response."
      st.success(msg)
    else:
      st.error(f"Backend error: {res.status_code}")


if load_btn:
  payload = {"repo_name": sel_repo} if sel_repo else {}
  res = requests.post(GET_ART_ENDPOINT, json=payload)
  if res.status_code == 200:
    data = res.json().get("reports", [])
    if data and isinstance(data[0], dict):
      st.subheader(f"📄 {data[0].get('path','docs.md')}")
      st.download_button("Download docs.md", data[0].get('content','').encode('utf-8'), file_name='docs.md')
      st.markdown("---")
      st.markdown(data[0].get('content',''))
    else:
      st.info("No artifact found.")
  else:
    st.error(f"Backend error: {res.status_code}")


# Optional: smooth scroll to bottom when new content arrives
components_html("""
<script>
setTimeout(()=>{window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'})},100);
</script>
""", height=0)