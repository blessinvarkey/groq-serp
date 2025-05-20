Masking PII in free-form text—even with LLM help—comes with several pitfalls and edge cases:

Incomplete or Overzealous Masking
False negatives: Rare or unexpected identifiers (e.g. internal employee IDs, obscure usernames) can slip through if your model’s training data never saw that pattern.
False positives: Common words or public figures might get masked unintentionally, degrading the conversational quality.
Context Sensitivity
Names like “Apple” or “Jordan” can be either brand names or personal names. Without broader context, it’s hard to decide whether to mask, and incorrect masking can introduce confusion.
Chained or Nested PII
Compound identifiers—“Dr. A. Smith, license #XY-1234, from 123 Main St.”—require multi-pass or hierarchical masking. A simple regex or single LLM pass may only catch part of it.
Maintaining Readability and Meaning
Over-masking can strip away too much context (“<NAME_1> went to <PLACE_1>”), making follow-up questions or answers incoherent. Striking the right balance between privacy and usability is non-trivial.
Mapping Consistency Across Turns
If the same entity appears twice (“Alice” in Q1 and Q2), your mapping must use the same placeholder (<NAME_1>) to allow coherent unmasking. Keeping a persistent mapping grows complex in multi-turn flows.
Latency and Cost
Each mask/unmask step is another LLM API call, doubling your round trips. In low-latency or high-volume environments this quickly adds cost and slows down the user experience.
Regulatory and Legal Nuances
Different jurisdictions have different definitions of “sensitive” PII (e.g. GDPR’s “special categories”). Your masking policy needs to be auditable and configurable to comply with local laws.
Debugging and Fail-Safe Modes
If masking fails (e.g. JSON parse errors), you need a clear fallback: either abort the request or proceed with a safe default. Silent failures can inadvertently leak PII.
Mitigations

Combine LLM masking with lightweight regex or deterministic rules for known patterns.
Maintain a persistent, turn-level mapping store to reuse placeholders consistently.
Expose debugging UIs (like we built) only in dev or admin modes to tune masking prompts.
Regularly review masked vs. unmasked pairs to catch new edge cases.
Balancing privacy, accuracy, and usability in PII masking is an ongoing, iterative process—especially when relying on generative models that can be unpredictable
