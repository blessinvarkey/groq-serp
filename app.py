import streamlit as st
import os
import requests
import json
import re
import time
from json.decoder import JSONDecodeError

# Import the RateLimitError class
from groq import RateLimitError

# … your existing setup (page config, keys, serp_search, etc.) …

def call_llm(prompt, max_tokens=4096):
    """Route prompt to GROQ LLM with retry/backoff on rate limits."""
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
                # wait and retry
                time.sleep(backoff)
                backoff *= 2
            else:
                # out of retries: propagate
                raise

def on_enter():
    user_input = st.session_state.user_input.strip()
    if not user_input:
        return

    try:
        # … your existing PII-masking and SERP steps …

        # 4. Call the LLM (now with built-in retry)
        masked_ans = call_llm(llm_prompt)
        final = unmask_pii(masked_ans, turn_map)

    except RateLimitError:
        # show friendly message
        st.error("⚠️ Sorry, the LLM service is currently overloaded. Please wait a moment and try again.")
        return

    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return

    # … store last_turn and clear input as before …
