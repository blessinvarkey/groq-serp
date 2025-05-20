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
st.title("Groq-SERP-llama-3.3-70b Chatbot with PII Masking & SERP Debug")

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
    """Call Serper REST API and return JSON results + URL + params."""
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY}
    params = {"q": query}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json(), url, params

def call_llm(prompt, max_tokens=4096):
    """Route prompt to GROQ LLM; raise error if client missing."""
    if not groq_client:
        return "Error: GROQ_API_KEY not provided."
    response = groq_client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=max_tokens
    )
    return response.choices[0].message.content

# --------------------------------
# PII-masking / unmasking helpers
# --------------------------------
def mask_pii(text):
    """
    Mask only private or sensitive PII in `text`, leaving
    public or widely known info untouched.
    Returns masked_text and mapping.
    """
    mask_prompt = (
        "Identify and mask any **private or sensitive** PII in the following text.  \n"
        "- **Do NOT** mask names or details that are publicly known (e.g. public figures, "
        "company names, known landmarks).  \n"
        "- Only mask personal emails, personal phone numbers, private addresses, "
        "and other non-public identifiers.  \n\n"
        f"Text:\n'''{text}'''\n\n"
        "Return *only* a JSON object with keys:\n"
        "  • masked_text  \n"
        "  • mapping  \n"
        "No extra explanation."
    )
    raw = call_llm(mask_prompt)

    # Try direct JSON parse
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        # Fallback: extract first {...} block
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            st.error("PII masking JSON parse failed. Raw output:")
            st.code(raw)
            st.stop()
        try:
            data = json.loads(m.group())
        except JSONDecodeError:
            st.error("PII masking JSON parse failed after regex. Raw JSON:")
            st.code(m.group())
            st.stop()

    # Verify expected structure
    if "masked_text" not in data or "mapping" not in data:
        st.error("PII mask JSON missing required keys. Parsed data:")
        st.json(data)
        st.stop()

    masked = data["masked_text"]
    mapping = data["mapping"]

    # Fallback regex mask if mapping is empty
    if not mapping:
        # mask names like First Last
        nm = re.search(r'([A-Z][a-z]+ [A-Z][a-z]+)', text)
        if nm:
            placeholder = "<NAME_1>"
            mapping[placeholder] = nm.group(1)
            masked = masked.replace(nm.group(1), placeholder)
        # mask any 4+ digit sequence
        idm = re.search(r'\b(\d{4,})\b', text)
        if idm:
            placeholder = "<ID_1>"
            mapping[placeholder] = idm.group(1)
            masked = masked.replace(idm.group(1), placeholder)

    return masked, mapping

def unmask_pii(text, mapping):
    """Restore placeholders back to the original PII."""
    for ph, orig in mapping.items():
        text = text.replace(ph, orig)
    return text

# -------------------------
# Initialize last-turn holder
# -------------------------
if "last_turn" not in st.session_state:
    st.session_state.last_turn = None

# -------------------------------------------------
# Callback: run when user presses Enter in textbox
# -------------------------------------------------
def on_enter():
    user_msg = st.session_state.user_input.strip()
    if not user_msg:
        return

    # 1. Mask PII
    masked_query, pii_map = mask_pii(user_msg)

    # 2. SERP search on masked query
    with st.spinner("Searching external data…"):
        serp_results, serp_url, serp_params = serp_search(masked_query)

    # 3. Build LLM prompt
    llm_prompt = (
        "You are a helpful assistant. Use the following search results to answer the question.\n"
        f"Search results (JSON): {json.dumps(serp_results)}\n\n"
        f"Question: {masked_query}\n\n"
        "Please provide a clear, accurate, and fully scoped answer."
    )

    # 4. Get final answer (unmasked)
    with st.spinner("Generating answer…"):
        try:
            masked_answer = call_llm(llm_prompt)
        except Exception as e:
            masked_answer = f"Error from GROQ: {e}"
    final_answer = unmask_pii(masked_answer, pii_map)

    # 5. Store this turn’s debug info
    st.session_state.last_turn = {
        "masked_query": masked_query,
        "pii_map": pii_map,
        "serp_url": serp_url,
        "serp_params": serp_params,
        "serp_results": serp_results,
        "final_answer": final_answer
    }

    # 6. Clear input
    st.session_state.user_input = ""

# --------------------------
# Input box (Enter-to-send)
# --------------------------
st.text_input(
    label="",
    key="user_input",
    on_change=on_enter,
    placeholder="Type your message and press Enter…"
)

# --------------------------
# Render only the most recent turn
# --------------------------
turn = st.session_state.last_turn
if turn:
    st.markdown("---")
    st.subheader("🔒 Masked Query")
    st.write(turn["masked_query"])

    st.subheader("🗺️ PII Mapping")
    st.json(turn["pii_map"])

    st.subheader("🔎 Serper API Request")
    st.write(f"URL: {turn['serp_url']}")
    st.json(turn["serp_params"])

    st.subheader("📦 Serper API Response")
    st.json(turn["serp_results"])

    st.subheader("✅ Final Unmasked Answer")
    st.write(turn["final_answer"])
