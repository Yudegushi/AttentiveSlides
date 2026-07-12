# Streamlit Grounded XAI

## Purpose

`apps/streamlit_grounded_xai.py` presents the API-backed grounded
TutorAgent with learner-visible provenance and uncertainty.

The interface displays:

- tutor answer;
- confirmed AOI;
- claim-to-source mapping;
- source previews;
- grounding validation;
- external-knowledge status;
- latency, token usage, retry count, and fallback status;
- sanitized attempt outcomes.

The interface does not display:

- raw Chain-of-Thought;
- raw provider responses;
- API keys;
- provider request IDs;
- complete prompts.

## Run

Load the DashScope environment:

```bash
source /root/autodl-tmp/secrets/dashscope.env
