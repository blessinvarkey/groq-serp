# Groq‑SERP Chatbot with PII Masking

A conversational assistant built with Streamlit, Serper Search API, and GROQ LLM. It masks sensitive PII before external calls, handles rate limits, and optionally displays debug info in the sidebar.

---

## Features

* **PII Masking**: Combines regex, NER, and LLM prompts to replace private data (emails, phone numbers, IDs, names) with placeholders.
* **Serper Web Search**: Real‑time search via Serper REST API.
* **GROQ LLM Integration**: Answers built from search results using `llama-3.3-70b-versatile`.
* **Rate Limit Handling**: Exponential backoff on GROQ rate limits.
* **Debug Mode**: Toggle in sidebar to inspect placeholders, API requests, and responses.
* **Enter‑to‑Send UI**: No send button—press Enter to submit.

---

## Repository Contents

```plaintext
├── app.py            # Main Streamlit application
├── requirements.txt  # Python dependencies
└── README.md         # This file
```

---

## Requirements

Specify in `requirements.txt`:

```txt
streamlit
requests
groq
spacy
pytz
```

Additionally, install the spaCy model:

```bash
python -m spacy download en_core_web_sm
```

---

## Configuration

Set your API keys via Streamlit secrets or environment variables:

* `GROQ_API_KEY`: Your Groq API key
* `SERPER_API_KEY`: Your Serper API key

**Streamlit Cloud (streamlit.app)**

1. Push this repo to GitHub.
2. In your Streamlit Cloud dashboard, "New app" → connect repo → select branch/file.
3. Under "Settings" → "Secrets" add `GROQ_API_KEY` and `SERPER_API_KEY`.

**Local (optional)**

```bash
export GROQ_API_KEY="<your-groq-key>"
export SERPER_API_KEY="<your-serper-key>"
```

---

## Running the App

Locally:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Streamlit Cloud:

* Once deployed, open the app URL.
* Type your query in the input box and press **Enter**.

---

## Usage

1. **Input**: Enter any question—PII (names, IDs, emails) will be masked automatically.
2. **Process**:

   * Regex & NER mask common PII.
   * LLM catch‑all mask for edge cases.
   * Masked query sent to Serper and GROQ LLM.
   * Final LLM answer is unmasked for display.
3. **Output**: Only the final unmasked answer appears in the main area.
4. **Debug**: Enable "Debug mode" in the sidebar to view:

   * Global placeholder map.
   * This turn’s masked query & mapping.
   * Raw SERP request and JSON response.

---

## Customization

* Adjust regex patterns in `mask_pii` for additional data types.
* Swap NER model (e.g. `en_core_sci_sm`) for domain‑specific entity detection.
* Tweak retry/backoff in `call_llm` for different rate‑limit strategies.

---

## Troubleshooting

* **Blank page**: Ensure no unsupported Python syntax (remove new‑style annotations).
* **JSONDecodeError**: Enable debug mode to inspect raw LLM outputs and refine prompts.
* **RateLimitError**: Increase retry count or backoff, or upgrade your Groq plan.

---

