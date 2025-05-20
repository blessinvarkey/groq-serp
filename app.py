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
st.title("Groq-SERP-llama-3.3-70b Chatbot with Conditional PII Masking")

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
def serp_search(query: str) -> dict:
    url = "https://google.serper.dev/search"
    headers = {"X-API-KEY": SERPER_API_KEY}
    params = {"q": query}
    resp = requests.get(url, headers=headers, params=params)
    resp.raise_for_status()
    return resp.json(), url, params

def call_llm(prompt: str, max_tokens: int = 4096) -> str:
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
def mask_pii(text: str) -> tuple[str, dict]:
    """
    Mask only private or sensitive PII in `text`, leaving
    public or widely known names/info untouched.
    Returns (masked_text, mapping).
    """
    mask_prompt = (
        "Identify and mask any **private or sensitive** PII in the following text.  \n"
        "- **Do NOT** mask names or details that are publicly known (e.g. public figures, "
        "company names, known landmarks, public domain info).  \n"
        "- Only mask personal emails, personal phone numbers, private addresses, "
        "and other non-public identifiers.  \n\n"
        f"Text:\n'''{text}'''\n\n"
        "Return *only* a JSON object with keys:\n"
        "  • `masked_text` (the text with placeholders for masked PII)  \n"
        "  • `mapping` (dictionary of placeholder → original PII)\n"
        "No extra explanation."
    )
    raw = call_llm(mask_prompt)

    # Try direct JSON parse
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        # Fallback: extract the first {...} block
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            st.error("PII masking JSON parse failed. Raw output:")
            st.code(raw)
            raise
        try:
            data = json.loads(m.group())
        except JSONDecodeError:
            st.error("PII masking JSON parse failed after regex. Raw JSON:")
            st.code(m.group())
            raise

    # Verify expected structure
    if "masked_text" not in data or "mapping" not in data:
        st.error("PII mask JSON missing required keys. Parsed data:")
        st.json(data)
        raise ValueError("Unexpected PII mask format")

    return data["masked_text"], data["mapping"]

def unmask_pii(text: str, mapping: dict) -> str:
    for placeholder, original in mapping.items():
        text = text.replace(placeholder, original)
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

    # 1. Mask user PII (conditionally)
    masked_query, pii_map = mask_pii(user_msg)

    # 2. Perform external search
    with st.spinner("Searching external data…"):
        search_results, serp_url, serp_params = serp_search(masked_query)

    # 3. Build LLM prompt with masked_query
    llm_prompt = (
        "You are a helpful assistant. Use the following search results to answer the question.\n"
        f"Search results (JSON): {json.dumps(search_results)}\n\n"
        f"Question: {masked_query}\n\n"
        "Please provide a clear, accurate, and fully scoped answer."
    )

    # 4. Get masked answer
    with st.spinner("Generating answer…"):
        try:
            masked_answer = call_llm(llm_prompt)
        except Exception as e:
            masked_answer = f"Error from GROQ: {e}"

    # 5. Unmask the answer
    final_answer = unmask_pii(masked_answer, pii_map)

    # 6. Save this single-turn debug info
    st.session_state.last_turn = {
        "masked_query": masked_query,
        "pii_map": pii_map,
        "serp_url": serp_url,
        "serp_params": serp_params,
        "masked_answer": masked_answer,
        "final_answer": final_answer
    }

    # 7. Clear input
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

    st.subheader("🤖 Masked Answer")
    st.write(turn["masked_answer"])

    st.subheader("✅ Final Unmasked Answer")
    st.write(turn["final_answer"])
