# Voice Stage 1: Speech Output Baseline

## Scope

Stage 1 adds speech output for an existing tutor answer. It does not
capture microphone input and does not provide continuous conversation.

## Pipeline

1. `GroundedTutorAgent` produces the authoritative text answer.
2. The exact final answer text is passed to the speech adapter.
3. Alibaba Cloud Bailian `qwen3-tts-instruct-flash` synthesizes speech.
4. Temporary provider audio is downloaded immediately.
5. The WAV file is stored outside the repository.
6. Only sanitized metadata is retained.

## Default configuration

- Provider: Alibaba Cloud Bailian
- Model: `qwen3-tts-instruct-flash`
- Voice: `Cherry`
- Language: `Chinese`
- Output format: WAV
- Environment variable: `DASHSCOPE_API_KEY`

## Privacy boundary

The speech request contains only final tutor answer text and speech
style configuration.

The request must not include:

- raw camera frames
- gaze measurements
- microphone recordings
- facial landmarks
- calibration data
- hidden prompts
- hidden reasoning
- provider credentials

The public result must not contain:

- API keys
- temporary provider URLs
- provider request IDs
- raw provider responses

## Failure behavior

Speech generation failure must not remove or invalidate the grounded
text answer. Text remains the authoritative tutor response.

## Test separation

Unit tests use injected provider and download functions. They must not
make network requests.

The real provider is called only by:

```bash
python scripts/smoke_test_bailian_tts.py

##Deferred work

Stage 2 adds microphone capture and ASR.

Stage 3 adds continuous dialogue, VAD, noise rejection, turn detection,
response gating, interruption handling, and low-latency speech output.
