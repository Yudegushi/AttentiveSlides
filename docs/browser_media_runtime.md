# Browser media transport runtime

## Selected transport

Checkpoint 1 attempted streamlit-webrtc 0.75.0 first. In the real AutoDL
environment reached through a single SSH TCP forward, the browser could open its
camera and microphone but WebRTC never reached playing: after 30 seconds the
probe still reported zero video FPS, zero audio chunks, and empty queues. This is
reproducible transport-gate evidence, not a browser-permission or inference
failure. HTTP/WebSocket control traffic crosses the tunnel, but the WebRTC
ICE/RTP media path needs connectivity that the TCP-only forwarding setup does
not provide.

The selected AutoDL live transport is therefore the single-port fallback:
apps/single_port_media_fallback.py. It serves its capture page and all
/media/* endpoints from one HTTP origin. The old Streamlit WebRTC probe remains
as diagnostic evidence only; it is not the default live path on AutoDL.

No MediaPipe, VAD, Whisper, LLM, slide processing, or raw-media persistence is
part of either Checkpoint 1 path.

## Packet and queue contract

The fallback reuses the public modules.media.BrowserMediaSource contract:

- VideoPacket.frame is a frozen contiguous BGR numpy.ndarray, dtype uint8,
  shape (height, width, 3). Browser frames are JPEG encoded at most five times
  per second, decoded server-side, and limited to 320×240 before queueing.
- AudioPacket.samples is frozen interleaved little-endian signed-16 PCM,
  dtype int16, shape (samples, 1), sample rate 16,000 Hz.
- Both fallback packet types use a single browser-document clock:
  timestamp_clock="browser_performance_seconds" and a performance.now()/1000
  timestamp. This is suitable for aligning the two streams inside one browser
  session; it is not an AutoDL wall-clock timestamp.
- BrowserMediaSource.video_queue retains three newest frames. Its
  audio_queue retains at most 100 chunks and 4 MiB. push(), get_nowait(),
  qsize(), empty(), clear(), accepted count, last timestamp, drop count,
  overrun count, and current bytes remain the only queue API.

The browser permits at most one outstanding video upload and one outstanding
audio upload. Uploads that would accumulate client-side are dropped and counted
in the page status. Server payload limits are 512 KiB for JPEG and 128 KiB for
PCM; malformed, oversized, stale-session, or non-16 kHz mono chunks are
rejected before they reach a queue.

## Lifecycle and cleanup

The page gets both browser tracks before it calls /media/start. A generated
session token is required for every mutating request. Starting a new page
replaces and clears an old session; stale pages cannot enqueue or stop the newer
session.

The page sends a one-second heartbeat and posts /media/stop on OFF. It also
uses a page-hide beacon. The server has one 250 ms watchdog task: after two
seconds with no active session traffic it calls
BrowserMediaSource.stop(reason="browser inactive"), which closes and clears
both queues. start() and stop() remain idempotent. No endpoint writes raw
video or audio to disk, and the server is documented to bind loopback only.

## AutoDL installation and launch

From /root/autodl-tmp/workspace/AttentiveSlides-live-system:

~~~bash
/root/miniconda3/envs/attentive-app/bin/python -m pip install -r requirements-media.txt
/root/miniconda3/envs/attentive-app/bin/python \
  apps/single_port_media_fallback.py \
  --host 127.0.0.1 \
  --port 8501
~~~

From the browser machine:

~~~bash
ssh -N -L 8501:127.0.0.1:8501 AutoDL
~~~

Open http://localhost:8501. Browser localhost is a secure context for
camera/microphone permission, and every media request uses a relative same-origin
path through that one SSH-forwarded TCP port.

During this checkpoint, remote port 8501 was already occupied by an unrelated
existing Streamlit process in the original repository worktree. That process was
not stopped. For the isolated probe only, run the fallback on remote 8502 and
retain a single local forwarding port:

~~~bash
# AutoDL
/root/miniconda3/envs/attentive-app/bin/python \
  apps/single_port_media_fallback.py --host 127.0.0.1 --port 8502

# browser machine
ssh -N -L 8501:127.0.0.1:8502 AutoDL
~~~

This is a port-conflict deviation from the literal example, not a second exposed
transport port: the browser still accesses only http://localhost:8501.

Measured dependency versions:

- Python 3.10.20, Streamlit 1.59.1
- streamlit-webrtc 0.75.0, aiortc 1.14.0, av 16.1.0
- aiohttp 3.14.1, OpenCV 4.13.0.92
- torch unchanged at 2.7.1+cu118 (CUDA build 11.8)

## Verification status

Automated media tests use synthetic JPEG/PCM payloads only; they do not request
a physical camera/microphone or call any API. They cover packet conversion,
bounded queues, stale-session rejection, payload limits, idempotent lifecycle,
and inactivity cleanup.

Real-browser fallback acceptance remains **not verified** until it is observed
through the SSH tunnel:

1. grant camera and microphone; press ON and observe non-zero video FPS and audio
   chunks/s;
2. press OFF and observe queues/stats stop within two seconds;
3. refresh or close the page and observe cleanup state
   stopped: browser inactive (or browser stopped);
4. leave ON for three minutes and confirm queue depths stay bounded while any
   drops/overruns remain visible.

The fallback is live browser transport, not a manual-upload substitute.
