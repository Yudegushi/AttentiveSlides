# Voice Stage 2: Browser Microphone and Local STT

## Scope

Stage 2 captures browser microphone audio, performs local voice turn
detection and speech recognition, previews the transcript, and lets
the user explicitly copy it into the existing command field.

Stage 2 does not automatically call the tutor.

## Pipeline

Browser microphone
→ 16 kHz mono signed-16 PCM
→ bounded in-memory queue
→ WebRTC VAD
→ speech turn detector
→ temporary WAV
→ local faster-whisper
→ transcript preview
→ explicit Use transcript action

## Privacy

- Camera permission is not requested.
- Raw audio is not sent to the cloud tutor.
- Audio chunks remain in bounded memory.
- Temporary turn WAV files are deleted after transcription.
- Only accepted transcript text enters the existing interaction flow.

## Default STT configuration

- Engine: faster-whisper
- Model: small multilingual
- Device: CUDA
- Compute type: float16
- Language: zh
- Beam size: 1

## Transport

- Streamlit: loopback port 8502
- Microphone ingress: loopback port 8503
- Both ports are forwarded through SSH.
- Browser audio is posted to the microphone ingress using session IDs,
  bounded payloads, heartbeat cleanup, and 16 kHz mono PCM validation.

## Stage 3 reuse

Stage 3 will retain the same browser transport, VAD, turn detector,
worker, and controller. It will add:

1. transcript validity and noise filtering;
2. response gating;
3. automatic tutor invocation;
4. TTS playback;
5. echo and interruption control;
6. continuous dialogue state management.
