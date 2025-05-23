import streamlit as st
import os
import requests
import json
import re
import time
from json.decoder import JSONDecodeError

# GROQ client & rate-limit exception
from groq import Groq, RateLimitError
# Phoenix Evals imports (install via pip install arize-phoenix-evals)
from phoenix.evals import run_evals, QAEvaluator, HallucinationEvaluator

# -------------
# Page config
# -------------
st.set_page_config(page_title="Groq-SERP Chatbot", layout="wide")

# --------------------------
# Debug mode toggle in sidebar
# --------------------------
debug_mode = st.sidebar.checkbox("Debug mode", value=False)

# -------------
# Load API keys
# -------------
GROQ_API_KEY   = st.secrets.get("GROQ_API_KEY")   or os.getenv("GROQ_API_KEY")
SERPER_API_KEY = st.secrets.get("SERPER_API_KEY") or os.getenv("SERPER_API_KEY")
OPENAI_API_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")

# Initialize GROQ client
if GROQ_API_KEY:
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None

# Initialize Phoenix evaluators
qa_eval    = QAEvaluator()
hallu_eval = HallucinationEvaluator()

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
        return "Error: missing GROQ_API_KEY."
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
# Persistent global mapping across turns
# ---------------------------------
if "global_mapping" not in st.session_state:
    st.session_state.global_mapping = {}
if "placeholder_counter" not in st.session_state:
    st.session_state.placeholder_counter = {"NAME":0,"EMAIL":0,"PHONE":0,"ID":0}

def _next_placeholder(kind):
    st.session_state.placeholder_counter[kind] += 1
    return f"<{kind}_{st.session_state.placeholder_counter[kind]}>"

# --------------------------------
# Combined Regex + LLM Masking
# --------------------------------
def mask_pii(text):
    mapping = st.session_state.global_mapping
    masked = text

    # 1) regex for emails
    for match in re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text):
        ph = next((k for k,v in mapping.items() if v==match), None) or _next_placeholder("EMAIL")
        mapping[ph] = match
        masked = masked.replace(match, ph)

    # 2) regex for phone numbers
    for match in re.findall(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", text):
        ph = next((k for k,v in mapping.items() if v==match), None) or _next_placeholder("PHONE")
        mapping[ph] = match
        masked = masked.replace(match, ph)

    # 3) regex for long numeric IDs
    for match in re.findall(r"\b\d{4,}\b", text):
        ph = next((k for k,v in mapping.items() if v==match), None) or _next_placeholder("ID")
        mapping[ph] = match
        masked = masked.replace(match, ph)

    # 4) LLM catch-all for any other private PII
    llm_prompt = (
        "Mask any *other* private or sensitive PII in this text, "
        "but leave public figures and company names untouched.\n\n"
        f"Text:\n'''{masked}'''\n\n"
        "Return *only* JSON with keys `masked_text` and `mapping`."
    )
    raw = call_llm(llm_prompt)
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            if debug_mode:
                st.sidebar.error("LLM mask raw:")
                st.sidebar.code(raw)
            st.stop()
        data = json.loads(m.group())

    for ph, orig in data["mapping"].items():
        if ph not in mapping:
            mapping[ph] = orig
    masked = data["masked_text"]

    turn_map = {ph: mapping[ph] for ph in data["mapping"]}
    return masked, turn_map

def unmask_pii(text, turn_map):
    for ph, orig in turn_map.items():
        text = text.replace(ph, orig)
    return text

# -------------------------
# Single-turn holder
# -------------------------
if "last_turn" not in st.session_state:
    st.session_state.last_turn = None

def on_enter():
    user_input = st.session_state.user_input.strip()
    if not user_input:
        return

    try:
        # Mask PII
        masked_q, turn_map = mask_pii(user_input)

        # SERP search
        serp_res, serp_url, serp_params = serp_search(masked_q)

        # LLM answer (masked)
        prompt = (
            "You are a helpful assistant. Use these results:\n"
            f"{json.dumps(serp_res)}\n\n"
            f"Question: {masked_q}"
        )
        masked_ans = call_llm(prompt)

        # Phoenix evals
        qa_metrics = run_evals(
            dataframe=pd.DataFrame([{"input": masked_q, "output": masked_ans, "reference": d.get("snippet","")} for d in serp_res.get("organic",[])]),
            evaluators=[qa_eval],
            provide_explanation=True
        )
        hallu_metrics = run_evals(
            dataframe=pd.DataFrame([{"input": masked_q, "output": masked_ans, "context": json.dumps(serp_res)}]),
            evaluators=[hallu_eval],
            provide_explanation=True
        )

        # Unmask answer
        final = unmask_pii(masked_ans, turn_map)

        # Store last turn
        st.session_state.last_turn = {
            "masked_query": masked_q,
            "turn_map": turn_map,
            "serp_url": serp_url,
            "serp_params": serp_params,
            "serp_response": serp_res,
            "qa_metrics": qa_metrics,
            "hallu_metrics": hallu_metrics,
            "final_answer": final
        }

    except RateLimitError:
        st.error("⚠️ Rate limit exceeded. Please wait and try again.")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    finally:
        st.session_state.user_input = ""

# --------------------------
# Input box
# --------------------------
st.text_input(
    "", key="user_input",
    on_change=on_enter,
    placeholder="Type your message and press Enter…"
)

# --------------------------
# Render UI
# --------------------------
turn = st.session_state.last_turn
if turn:
    # Main UI: only final answer
    st.subheader("✅ Final Answer")
    st.write(turn["final_answer"])

    # Debug sidebar
    if debug_mode:
        st.sidebar.markdown("### 🔒 Masked Query")
        st.sidebar.write(turn["masked_query"])

        st.sidebar.markdown("### 🗺️ This Turn’s Mapping")
        st.sidebar.json(turn["turn_map"])

        st.sidebar.markdown("### 🔎 SERP Request")
        st.sidebar.write(turn["serp_url"])
        st.sidebar.json(turn["serp_params"])

        st.sidebar.markdown("### 📦 SERP Response")
        st.sidebar.json(turn["serp_response"])

        st.sidebar.markdown("### 📊 QA Metrics")
        st.sidebar.write(turn["qa_metrics"].to_dict())

        st.sidebar.markdown("### ⚠️ Hallucination Metrics")
        st.sidebar.write(turn["hallu_metrics"].to_dict())
