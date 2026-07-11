# Audio merge-readiness checklist

Status: **not ready for merge to `main`**. This document records verified local work and
the remaining real-audio gates. It does not authorize a merge.

## Branch snapshot

- Branch: `codex-audio-first-step`
- Audio usability implementation baseline: `bb77f7ca5292c8dbaff4ee8c188259b7df7feeab`
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

## Real-audio gates still required

1. Confirm the actual Git repository path on `LenovoLinux_Dorm`. The candidate
   `/home/charles/attentive_slides_eval_work` exists but is not a Git repository.
2. Sync this branch and the confirmed private recordings into an ignored remote
   `data/audio_eval/user_smoke/` directory.
3. On `pyboe`, verify CUDA and faster-whisper, then run `fast` and `balanced`:

   ```bash
   python evaluation/eval_audio_usability.py \
     --manifest data/audio_eval/user_smoke_manifest.csv \
     --audio-root data/audio_eval/user_smoke \
     --engine faster_whisper --profile fast \
     --output data/audio_eval/results/user_smoke_fast.json

   python evaluation/eval_audio_usability.py \
     --manifest data/audio_eval/user_smoke_manifest.csv \
     --audio-root data/audio_eval/user_smoke \
     --engine faster_whisper --profile balanced \
     --output data/audio_eval/results/user_smoke_balanced.json
   ```

4. Generate `profile_comparison.md` and choose the real demo default from its semantic
   metrics and latency. No real-audio recommendation exists until these commands finish.
5. Perform the user-triggered record-to-transcribe check on the 4060. This requires a
   user recording and any necessary microphone/browser permission; do not replace it with
   streaming ASR.
6. Review `git status --short` and ignore rules again immediately before any main-merge
   request. A merge to `main` still requires explicit user approval.

## Known limitations

- All local results above use deterministic mocks, not the ten private recordings.
- The Streamlit audio flow has unit coverage but its browser input/permission path still
  requires manual verification on the target machine.
- CPU remains fallback-only; it is not a recommended primary demo profile.
