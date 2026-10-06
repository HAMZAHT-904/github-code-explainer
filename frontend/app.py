"""Streamlit UI. Calls FastAPI only — no cloning or LLM work happens here."""

import os

import requests
import streamlit as st

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")

st.set_page_config(page_title="GitHub Repository Code Explainer", layout="wide")
st.title("GitHub Repository Code Explainer")
st.caption("Paste a public GitHub URL. A local FastAPI backend clones the repo and a local Ollama model explains it.")

repo_url = st.text_input(
    "GitHub Repository URL:",
    placeholder="https://github.com/username/repository",
)

if st.button("Explain Repository", type="primary"):
    if not (repo_url or "").strip():
        st.error("Please enter a GitHub repository URL.")
    else:
        with st.spinner("Cloning the repository and generating an explanation with the local LLM..."):
            try:
                response = requests.post(
                    f"{BACKEND_URL}/explain",
                    json={"repo_url": repo_url.strip()},
                    timeout=300,
                )
            except requests.ConnectionError:
                st.error(
                    "Backend unavailable. Start FastAPI with: uvicorn backend.main:app --reload"
                )
            except requests.Timeout:
                st.error("The request timed out. The repository may be large or the local model is slow.")
            else:
                if response.status_code == 200:
                    explanation = (response.json() or {}).get("explanation", "")
                    if explanation:
                        st.markdown(explanation)
                    else:
                        st.error("The backend returned an empty explanation.")
                else:
                    try:
                        detail = response.json().get("detail")
                    except ValueError:
                        detail = response.text
                    if isinstance(detail, list):
                        detail = "; ".join(str(item) for item in detail)
                    st.error(str(detail) or f"Request failed with status {response.status_code}.")
