# Main UI Grounded Tutor Integration

## Workflow

```text
manual target
+ typed intent
+ explicit confirmation
+ cloud-text permission
→ TutorContext
→ GroundedTutorAgent
→ structured parsing
→ grounding validation
→ retry or deterministic fallback
→ learner-facing answer
→ sanitized XAI
API gating

The Main UI does not call the external provider unless:

the target and intent are explicitly confirmed;
the confirmed interaction is valid;
cloud-text permission is enabled;
DASHSCOPE_API_KEY is configured;
the learner presses Generate grounded answer.

Streamlit reruns do not automatically call the provider.

Uploaded decks

Uploaded PDFs do not use the mock-manifest ContextRetriever.

The Main UI constructs a TutorContext directly from:

the active rendered slide;
the confirmed AOI;
the confirmed context text;
the typed intent;
neighbor slide text;
interaction provenance.
Public output

Session state stores:

answer;
active-recall question;
uncertainty;
decision summary;
validation summary;
model telemetry;
sanitized claim-source XAI.

It does not store or expose:

API keys;
raw provider responses;
provider request IDs;
hidden Chain-of-Thought.
