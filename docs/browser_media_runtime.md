# Browser Media Runtime

## Selected formal transport

The selected AutoDL transport is the same-origin HTTP media path integrated into
`apps/streamlit_live.py`. `streamlit-webrtc` is not imported or called by the
formal UI. The old WebRTC probe may remain as diagnostic history, but it is not
a runtime transport and no ICE/STUN/TURN work is part of this release.

One public aiohttp listener is the only browser entry point:

```text
localhost:8501 over one SSH -L
├── /capture, /media/*  -> internal aiohttp ingress
└── everything else    -> internal Streamlit HTTP/WebSocket
```

The launcher waits up to 30 seconds for internal ingress `/health` and
Streamlit `/_stcore/health` before binding the public listener. It launches
Streamlit with `sys.executable -m streamlit`, inherits stdout/stderr, preserves
WebSocket subprotocols and binary/text frames, streams uploads in bounded
chunks, preserves duplicate response headers, rewrites internal redirects, and
exits when an already-healthy internal service later fails. Port conflicts fail
immediately; the launcher never silently selects another port.

## Shared source and packet contract

The cached formal resource graph constructs one `BrowserMediaSource`. That
exact object is owned by the controller and injected into
`FallbackMediaIngress`; there is no parallel source, queue, worker, or
controller.

- Video packets are frozen contiguous BGR `numpy.ndarray` values decoded from
  bounded JPEG. Browser capture is 320 pixels wide, quality 0.65, at most five
  uploads/s, with one upload in flight.
- Audio packets are frozen interleaved little-endian signed-16 PCM with shape
  `(samples, 1)`, 16,000 Hz mono, with one upload in flight.
- Both tracks use `performance.now()/1000` and
  `timestamp_clock="browser_performance_seconds"`.
- The video queue retains the three newest frames. The audio queue retains at
  most 100 chunks and 4 MiB. Drops and overruns remain visible.
- Server limits are 512 KiB per JPEG and 128 KiB per PCM request. Malformed,
  oversized, wrong-format, stale-session, and unarmed requests are rejected
  before queueing.
- No endpoint writes raw media to disk. Sensing, VAD, STT, tutor work, and
  Streamlit commands never run in an HTTP handler or media callback.

## Generation, freshness, and lifecycle

Ingress maintains one pending or active generation. A browser `/media/start`
registers a pending generation; the coordinator, not the HTTP handler, performs
replacement in this order:

1. pause readiness for the pending generation;
2. stop the old runtime, which may stop the shared source;
3. activate/reset the shared source for the current generation;
4. clear readiness and wait for new packets from that generation;
5. start the runtime only when both video and audio are fresh.

Freshness is based on the server monotonic receive clock, not merely on whether
a packet was ever seen. Both media tracks use a 2.0-second stale threshold; the
heartbeat timeout is 3.0 seconds. While running, stale video, stale audio,
heartbeat loss, explicit pagehide/stop, ended tracks, or persistent mute trigger
the same disconnect cleanup.

Start/stop, service creation, Streamlit reruns, and shutdown are idempotent.
Master OFF disarms ingress, stops controller and workers, stops the source,
clears both bounded queues, and makes stale browser sessions unable to enqueue
or stop a newer session. OFF or disconnect also clears an unfinished turn from
the live view model so a stopped runtime cannot present a stale correction.

## Capture component

Master ON embeds relative `/capture` using the Streamlit embedding API available
in Streamlit 1.59.1. The iframe is outside the 0.5-second periodic fragment, so
polling cannot recreate browser tracks. Installed Streamlit emits
`allow="camera; microphone; geolocation"` for the iframe.

Capture automatically attempts `getUserMedia({video: true, audio: true})`.
When browser autoplay/user-gesture policy blocks it, exactly one
**Grant camera/mic** button retries capture; this is permission recovery, not a
second lifecycle switch. The component sends a one-second heartbeat, registers
`ended`, `mute`, and `unmute` handlers for both tracks, sends a pagehide beacon,
closes the `AudioContext`, stops browser tracks, and clears timers on cleanup.

## Reproducible launch

See `docs/live_ui_usage.md` for the one-time MediaPipe/Whisper prerequisites.
With `ATTENTIVE_WHISPER_MODEL` set to a local faster-whisper-small snapshot:

```bash
# AutoDL
cd /root/autodl-tmp/workspace/AttentiveSlides-live-system
ATTENTIVE_WHISPER_MODEL=/absolute/local/snapshot \
/root/miniconda3/envs/attentive-app/bin/python \
  scripts/run_live_single_port.py \
  --host 127.0.0.1 --port 8501 \
  --streamlit-port 8502 --ingress-port 8503

# Browser machine: exactly one forwarded TCP port
ssh -N -L 8501:127.0.0.1:8501 AutoDL
```

Open <http://localhost:8501>. Internal 8502/8503 are loopback-only and are not
forwarded.

## Verification

Automated coverage uses synthetic JPEG/PCM and fake deterministic
sensing/transcription/tutor boundaries. It covers source identity, dual-track
freshness, single-track refusal, session replacement ordering, track staleness,
heartbeat/pagehide cleanup, OFF cleanup, rerun idempotency, multi-megabyte PDF
proxying, Streamlit WebSocket subprotocol/binary forwarding, redirects, headers,
cookies, confirmation resume, and correction overriding prediction.

The 2026-07-13 real-browser technical gate used one SSH mapping and the formal
UI. The embedded iframe obtained camera/microphone permission; the proxy passed
a 13,499,116-byte real course PDF with SHA-256
`9c3ea47a5746cb6681447b3a51fd125ddf17485412ec79629f3c2d20fd5601d8`;
media measured roughly 4.6–4.9 video frames/s and 9.1–10.8 audio chunks/s.
Five confirmation/final pairs completed without an app restart. Three final
records demonstrate correction overriding prediction (`block_4 -> block_6`,
`block_5 -> whole_slide`, and `block_4 -> block_10`); two retained the predicted
`block_4`. Canonical JSONL reached 14 lines from a one-line diagnostic baseline,
including five pending/final pairs plus three unfinished/noise attempts. Final
Master OFF reported inactive/disarmed ingress, stopped source/controller, zero
queue depth, zero drops/overruns, and cleanup state
`stopped: master switch off`.

The overlay now draws numbered AOI badges and confirmation choices use the same
number plus PDF-derived text, type, and internal ID. Dense slides can still have
many overlapping regions, and real-room VAD/STT can create unwanted pending
turns; one ambient-noise utterance was transcribed as Russian after the five
completed turns. These are known usability/accuracy limitations, not transport
failures. The standalone fallback is not accepted as substitute evidence.

The formal run also exposed concurrent AOI-manifest generation from Streamlit
and the sensing worker. `AOIManager` now serializes in-process manifest
mutations and atomic-file replacement, preventing the observed
`dictionary changed size during iteration` crash.
