# Audio merge-readiness checklist

Status: **not ready for merge to `main`**. Real-audio profile evaluation is complete;
the user-triggered recording and browser interaction gates remain. This document does not
authorize a merge.

## Branch snapshot

- Branch: `codex-audio-first-step`
- Audio usability implementation baseline: `4c94a82`
- Private source recordings: repository-root `audio_eval/` (Git-ignored)
- Reviewed manifest: `data/audio_eval/user_smoke_manifest.csv` (Git-ignored)

## Verified locally

The following commands were run on the local repository after implementation:

```bash
python -m unittest discover -s tests -v
python scripts/demo_tutor_loop.py
python scripts/demo_audio_to_tutor_loop.py \
  --audio data/audio_samples/right_figure.wav \
  --engine mock --profile fast \
  --sensing-preset high_confidence_right_figure
python evaluation/eval_reference_resolution.py
python evaluation/eval_scenario_outputs.py
```

Evidence at this snapshot:

- Unit suite: 75 tests passed.
- Mock audio-to-tutor flow completed through the adapter boundary.
- Reference-resolution metrics: intent, resolved AOI, confirmation mode, and adaptive
  strategy were all 1.0 across the eight deterministic scenarios.
- Scenario-output accuracy was 1.0 across the same deterministic scenarios.
- `audio_eval/`, `data/audio_eval/user_smoke_manifest.csv`, result directories, and JSONL
  logs are ignored. No private audio was included in the implementation commit.

## Verified on LenovoLinux_Dorm

- Clone: `/home/charles/repos/AttentiveSlides`, branch `codex-audio-first-step`.
- Environment: `pyboe`, Python 3.10.20, faster-whisper 1.2.1, and RTX 4060 Laptop GPU.
- The remote full suite passed: 78 tests.
- Streamlit 1.59.1 installed from `requirements-audio.txt`; a headless startup check
  reached `127.0.0.1:8501` and exited cleanly without microphone use.
- The 10 reviewed English `.m4a` files and the manifest mapped one-to-one. Audio, CSV,
  JSON results, and the Markdown comparison remained Git-ignored.

### Real-audio profile results

| Metric | fast | balanced |
|---|---:|---:|
| Transcript usable rate | 1.000 | 1.000 |
| Mean CER | 0.0846 | 0.0877 |
| Intent accuracy | 1.000 | 1.000 |
| Deictic detection accuracy | 1.000 | 1.000 |
| Explicit target hint accuracy | 1.000 | 1.000 |
| Confirmation mode accuracy | 1.000 | 1.000 |
| Response mode accuracy | 1.000 | 1.000 |
| Mean transcription latency | 348.0 ms | 476.4 ms |
| Mean end-to-end latency | 348.4 ms | 476.8 ms |

Recommendation: **fast** for both live and recorded demos. It retained the same semantic
scores as balanced while reducing end-to-end latency by about 27%. `accurate` was not run:
the required fast/balanced comparison already selected fast, and no remaining error pointed
to STT model capacity. CPU remains fallback-only.

## Real-audio gates still required

1. Perform the user-triggered record-to-transcribe check on the 4060. This requires a
   user recording and any necessary microphone/browser permission; do not replace it with
   streaming ASR.
2. Manually exercise the Streamlit flow in a browser: upload/select or record audio,
   click `Transcribe audio`, edit the transcript if needed, confirm/correct the AOI, and
   verify the final tutor response is withheld until confirmation.
3. Review `git status --short` and ignore rules again immediately before any main-merge
   request. A merge to `main` still requires explicit user approval.

## Known limitations

- The Streamlit browser input/permission path and an actual user-triggered short recording
  still require manual verification on the target machine.
- CPU remains fallback-only; it is not a recommended primary demo profile.
