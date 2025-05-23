import streamlit as st
import os
import requests
import json
import re
import time
from json.decoder import JSONDecodeError

# GROQ client & rate-limit exception
from groq import Groq, RateLimitError

# Configure OpenAI-compatible client for Phoenix (pointing at Groq)
import openai
import pandas as pd
from phoenix.evals import run_evals, QAEvaluator, HallucinationEvaluator
from phoenix.evals.models.openai import OpenAIModel

# -------------
# Page config
# -------------
st.set_page_config(page_title="Groq-SERP Chatbot", layout="wide")

# --------------------------
# Debug mode toggle
# --------------------------
debug_mode = st.sidebar.checkbox("Debug mode", value=False)

# -------------
# Load API keys
# -------------
GROQ_API_KEY   = st.secrets.get("GROQ_API_KEY")   or os.getenv("GROQ_API_KEY")
SERPER_API_KEY = st.secrets.get("SERPER_API_KEY") or os.getenv("SERPER_API_KEY")

# Point OpenAI client at Groq's OpenAI-compatible endpoint
openai.api_key = GROQ_API_KEY
openai.api_base = os.getenv("OPENAI_API_BASE", "https://api.groq.com/openai/v1")

# Initialize Groq chat client
groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

# Build a model wrapper for Phoenix Evals using OpenAIModel pointed at Groq
eval_model = OpenAIModel(
    api_key=GROQ_API_KEY,
    base_url=openai.api_base,
    model="llama-3.3-70b-versatile",
    temperature=0.0,
    max_tokens=256
)

# Instantiate Phoenix evaluators with the wrapped model
qa_eval    = QAEvaluator(eval_model)
hallu_eval = HallucinationEvaluator(eval_model)

# ----------------
# Helper functions
# ----------------
def serp_search(query):
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY}
    params = {"q": query}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json(), url, params


def call_llm(prompt, max_tokens=4096):
    if not groq_client:
        return "Error: GROQ_API_KEY not provided."
    backoff = 1
    for attempt in range(3):
        try:
            resp = groq_client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[{"role":"user","content":prompt}],
                max_tokens=max_tokens
            )
            return resp.choices[0].message.content
        except RateLimitError:
            if attempt < 2:
                time.sleep(backoff)
                backoff *= 2
            else:
                raise

# ---------------------------------
# Session state for mapping & counts
# ---------------------------------
if "global_mapping" not in st.session_state:
    st.session_state.global_mapping = {}
if "placeholder_counter" not in st.session_state:
    st.session_state.placeholder_counter = {"NAME":0, "EMAIL":0, "PHONE":0, "ID":0}

def _next_placeholder(kind):
    st.session_state.placeholder_counter[kind] += 1
    return f"<{kind}_{st.session_state.placeholder_counter[kind]}>"

# --------------------------------
# Mask PII: regex + LLM catch-all
# --------------------------------
def mask_pii(text):
    mapping = st.session_state.global_mapping
    masked = text
    # Regex masks
    for pattern, kind in [
        (r"[\w.+-]+@[\w-]+\.[\w.-]+", "EMAIL"),
        (r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", "PHONE"),
        (r"\b\d{4,}\b", "ID")
    ]:
        for match in re.findall(pattern, text):
            ph = next((k for k,v in mapping.items() if v==match), None) or _next_placeholder(kind)
            mapping[ph] = match
            masked = masked.replace(match, ph)
    # LLM catch-all
    llm_prompt = (
        "Mask any other private or sensitive PII in this text, leaving public figures untouched.\n"
        f"Text:\n'''{masked}'''\n"
        "Return only a JSON object with keys `masked_text` and `mapping`."
    )
    raw = call_llm(llm_prompt)
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            if debug_mode:
                st.error("Parsing PII mask failed:")
                st.code(raw)
            st.stop()
        data = json.loads(m.group())
    for ph, orig in data["mapping"].items():
        if ph not in mapping:
            mapping[ph] = orig
    masked = data["masked_text"]
    turn_map = {ph: mapping[ph] for ph in data["mapping"]}
    return masked, turn_map


def unmask_pii(text, turn_map):
    for ph, orig in turn_map.items(): text = text.replace(ph, orig)
    return text

# --------------------
# Single-turn holder
# --------------------
if "last_turn" not in st.session_state:
    st.session_state.last_turn = None

# -------------------------
# Callback on Enter
# -------------------------
def on_enter():
    user_input = st.session_state.user_input.strip()
    if not user_input:
        return
    # Mask & Search
    masked_q, turn_map = mask_pii(user_input)
    serp_res, serp_url, serp_params = serp_search(masked_q)
    # Generate masked answer
    llm_prompt = (
        "You are a helpful assistant. Use these Serper results:\n"
        f"{json.dumps(serp_res)}\n\n"
        f"Question: {masked_q}"
    )
    masked_ans = call_llm(llm_prompt)
    # Phoenix eval DataFrames
    qa_df = pd.DataFrame([
        {"input": masked_q, "output": masked_ans, "reference": item.get("snippet", "")} 
        for item in serp_res.get("organic", [])
    ])
    hallu_df = pd.DataFrame([
        {"input": masked_q, "output": masked_ans, "context": json.dumps(serp_res)}
    ])
    qa_metrics    = run_evals(dataframe=qa_df,    evaluators=[qa_eval],    provide_explanation=True)
    hallu_metrics = run_evals(dataframe=hallu_df, evaluators=[hallu_eval], provide_explanation=True)
    # Unmask & store final answer
    final_ans = unmask_pii(masked_ans, turn_map)
    st.session_state.last_turn = {
        "final_answer": final_ans,
        "qa_metrics": qa_metrics,
        "hallu_metrics": hallu_metrics
    }
    st.session_state.user_input = ""

# --------------------------
# Input widget
# --------------------------
st.text_input(
    "", key="user_input",
    on_change=on_enter,
    placeholder="Type your message and press Enter…"
)

# --------------------------
# Display response + metrics
# --------------------------
turn = st.session_state.last_turn
if turn:
    st.subheader("📢 Final Answer")
    st.write(turn["final_answer"])
    if debug_mode:
        st.markdown("---")
        st.subheader("📊 QA Metrics")
        df_qa = turn["qa_metrics"].results if hasattr(turn["qa_metrics"], 'results') else pd.DataFrame(turn["qa_metrics"])
        st.dataframe(df_qa)
        st.subheader("⚠️ Hallucination Metrics")
        df_h = turn["hallu_metrics"].results if hasattr(turn["hallu_metrics"], 'results') else pd.DataFrame(turn["hallu_metrics"])
        st.dataframe(df_h)
