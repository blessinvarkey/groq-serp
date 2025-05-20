import streamlit as st
import os
import requests
import json
import re
from json.decoder import JSONDecodeError

# -------------
# Page config
# -------------
st.set_page_config(page_title="Groq-SERP Chatbot", layout="wide")

# --------------------------
# Debug / Admin toggle
# --------------------------
debug_mode = st.sidebar.checkbox("Show debug info", value=False)

if debug_mode:
    st.sidebar.markdown("### Global PII Mapping")
    if "global_mapping" in st.session_state:
        st.sidebar.json(st.session_state.global_mapping)
    else:
        st.sidebar.write("⏳ none yet")

# -------------
# Load API keys
# -------------
GROQ_API_KEY = st.secrets.get("GROQ_API_KEY") or os.getenv("GROQ_API_KEY")
SERPER_API_KEY = st.secrets.get("SERPER_API_KEY") or os.getenv("SERPER_API_KEY")

if GROQ_API_KEY:
    from groq import Groq
    groq_client = Groq(api_key=GROQ_API_KEY)
else:
    groq_client = None

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
    resp = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role":"user","content":prompt}],
        max_tokens=max_tokens
    )
    return resp.choices[0].message.content

# ---------------------------------
# Persistent mapping across turns
# ---------------------------------
if "global_mapping" not in st.session_state:
    st.session_state.global_mapping = {}
if "placeholder_counter" not in st.session_state:
    st.session_state.placeholder_counter = {"NAME":0, "EMAIL":0, "PHONE":0, "ID":0}

def _next_placeholder(kind):
    st.session_state.placeholder_counter[kind] += 1
    return f"<{kind}_{st.session_state.placeholder_counter[kind]}>"

# --------------------------------
# Combined Regex + LLM Masking
# --------------------------------
def mask_pii(text):
    # 1) Deterministic regex for email/phone/IDs first
    mapping = st.session_state.global_mapping
    masked = text

    # email
    for match in re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text):
        if match not in mapping.values():
            ph = _next_placeholder("EMAIL")
            mapping[ph] = match
        else:
            # reuse existing placeholder
            ph = next(k for k,v in mapping.items() if v == match)
        masked = masked.replace(match, ph)

    # phone numbers (simple)
    for match in re.findall(r"\b\d{3}[-.\s]?\d{3}[-.\s]?\d{4}\b", text):
        if match not in mapping.values():
            ph = _next_placeholder("PHONE")
            mapping[ph] = match
        else:
            ph = next(k for k,v in mapping.items() if v == match)
        masked = masked.replace(match, ph)

    # long numeric IDs
    for match in re.findall(r"\b\d{4,}\b", text):
        if match not in mapping.values():
            ph = _next_placeholder("ID")
            mapping[ph] = match
        else:
            ph = next(k for k,v in mapping.items() if v == match)
        masked = masked.replace(match, ph)

    # 2) Ask LLM to catch anything else private/sensitive
    llm_prompt = (
        "Mask any *other* private or sensitive PII in this text, "
        "but leave public figures/names untouched.  \n\n"
        f"Text:\n'''{masked}'''\n\n"
        "Return *only* JSON with keys `masked_text` and `mapping`."
    )
    raw = call_llm(llm_prompt)

    # try parsing JSON
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            if debug_mode:
                st.error("LLM mask raw:")
                st.code(raw)
            st.stop()
        data = json.loads(m.group())

    # merge LLM mapping into global
    for ph, orig in data["mapping"].items():
        if ph not in mapping:
            mapping[ph] = orig
    masked = data["masked_text"]

    # return masked + the slice of mapping for *this* turn
    # (needed later to unmask)
    return masked, {k:v for k,v in mapping.items() if v in raw or v in text}

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

    # mask
    masked_q, turn_map = mask_pii(user_input)

    # search
    serp_res, serp_url, serp_params = serp_search(masked_q)

    # LLM answer
    prompt = (
        "You are a helpful assistant. Use these results:\n"
        f"{json.dumps(serp_res)}\n\n"
        f"Question: {masked_q}"
    )
    masked_ans = call_llm(prompt)
    final = unmask_pii(masked_ans, turn_map)

    st.session_state.last_turn = {
        "masked_query": masked_q,
        "turn_map": turn_map,
        "serp_url": serp_url,
        "serp_params": serp_params,
        "serp_response": serp_res,
        "final_answer": final
    }
    st.session_state.user_input = ""

# --------------------------
# UI: only current turn
# --------------------------
st.text_input(
    "", key="user_input",
    on_change=on_enter,
    placeholder="Type your message and press Enter…"
)

turn = st.session_state.last_turn
if turn:
    st.subheader("🔒 Masked Query")
    st.write(turn["masked_query"])

    if debug_mode:
        st.subheader("🗺️ This Turn’s Mapping")
        st.json(turn["turn_map"])

    st.subheader("✅ Final Answer")
    st.write(turn["final_answer"])
    
    st.subheader("🔎 SERP API Request")
    st.write(turn["serp_url"])
    st.json(turn["serp_params"])

    st.subheader("📦 SERP API Response")
    st.json(turn["serp_response"])

