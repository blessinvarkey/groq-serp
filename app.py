import re, json
from json.decoder import JSONDecodeError

def mask_pii(text: str) -> tuple[str, dict]:
    mask_prompt = (
        "Identify and mask any private PII in the following text.  \n"
        "Replace personal names with <NAME_1>, <NAME_2>, etc.  \n"
        "Replace IDs (any sequence of digits longer than 3) with <ID_1>, <ID_2>, etc.  \n"
        "Return *only* JSON with `masked_text` and `mapping`."
        f"\n\nText:\n'''{text}'''"
    )
    raw = call_llm(mask_prompt)

    # parse JSON (with the same fallback you already have)
    try:
        data = json.loads(raw)
    except JSONDecodeError:
        m = re.search(r'\{.*\}', raw, re.DOTALL)
        if not m:
            st.error("PII mask parse failed; raw output:")
            st.code(raw)
            raise
        data = json.loads(m.group())

    masked = data.get("masked_text", "")
    mapping = data.get("mapping", {})

    # Fallback: if mapping is empty, do a simple regex mask
    if not mapping:
        # mask any “Name Surname” pattern
        name_match = re.search(r'([A-Z][a-z]+ [A-Z][a-z]+)', text)
        if name_match:
            placeholder = "<NAME_1>"
            mapping[placeholder] = name_match.group(1)
            masked = masked.replace(name_match.group(1), placeholder)

        # mask any long digit sequence
        id_match = re.search(r'\b(\d{4,})\b', text)
        if id_match:
            placeholder = "<ID_1>"
            mapping[placeholder] = id_match.group(1)
            masked = masked.replace(id_match.group(1), placeholder)

    return masked, mapping
