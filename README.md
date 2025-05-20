# Groq-SERP Chatbot with PII Masking

A Streamlit app that integrates GROQ's LLM and Serper's search API to provide a conversational assistant with robust PII masking, rate-limit handling, and optional debugging features.

## Features

* 🔒 **PII Masking**: Combines regex, spaCy NER, and LLM-based masking to replace private or sensitive PII with placeholders before any external API calls.
* 🔎 **Serper Search**: Uses Serper REST API (`https://google.serper.dev/search`) for real-time web search results.
* 🤖 **GROQ LLM**: Routes prompts through GROQ's Python client to a conversational model (`llama-3.3-70b-versatile`).
* ⚙️ **Rate Limit Handling**: Automatic exponential backoff and retry logic on GROQ rate limit errors.
* 🐞 **Debug Mode**: Sidebar toggle to inspect global and turn-level PII mappings, SERP requests, and responses.
* 🚫 **Enter-to-Send**: Simplified UI with no send button—press Enter to submit a query.

## Requirements

Specify dependencies in your `requirements.txt`:

```txt
streamlit
requests
groq
spacy
en_core_web_sm
pytz
```

Install them with:

```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

## Configuration

Set your API keys as Streamlit secrets or environment variables:

* `GROQ_API_KEY`: Your Groq API key
* `SERPER_API_KEY`: Your Serper API key

Example using environment variables:

```bash
export GROQ_API_KEY="<your-groq-api-key>"
export SERPER_API_KEY="<your-serper-key>"
```

## Usage

Run the app locally:

```bash
streamlit run app.py
```

On streamlit.cloud, simply connect your repo, set the secrets in the UI, and deploy.

### Performing a Query

1. Type your message in the textbox and press **Enter**.
2. The app will:

   * Mask any private PII in your input
   * Send a masked version to Serper and the LLM
   * Unmask the final response and display only the answer

### Debug Mode

Toggle **Debug mode** in the sidebar to view:

* Global PII Mapping (all placeholders ↔ originals so far)
* This turn's masked query and mapping
* The raw SERP API request (URL + params)
* The full SERP API JSON response

Debug mode is intended for development and testing; keep it off in production.

## Code Structure

* `app.py` — Main Streamlit application
* **Masking pipeline**:

  * **Regex masks** for emails, phone numbers, IDs
  * **spaCy NER** for PERSON entities
  * **LLM catch-all** for any remaining private PII
* **Retry logic** in `call_llm` with exponential backoff on `RateLimitError`
* **Session state**:

  * `global_mapping` stores persistent placeholder → original PII across turns
  * `placeholder_counter` tracks incremental IDs for placeholders
  * `last_turn` holds only the most recent turn's debug info and answer

## Customization

* Adjust regex patterns in `mask_pii` for additional PII types.
* Extend NER with domain-specific models (e.g., `en_core_sci_sm` for medical data).
* Modify retry parameters or fallback strategies in `call_llm`.

## Troubleshooting

* **Blank screen**: Ensure your Python version supports the script (use standard annotations or remove unsupported syntax).
* **JSON parsing errors**: Inspect raw LLM outputs in Debug mode and refine prompts accordingly.
* **Rate limit errors**: Increase backoff, reduce token usage, or upgrade your Groq plan.

