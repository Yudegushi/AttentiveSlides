"""Optional local microphone recording helpers."""

from __future__ import annotations

from pathlib import Path


def record_wav(output_path: str, duration_sec: float, sample_rate: int = 16000) -> str:
    """Record a mono wav file and return the saved path."""
    try:
        import sounddevice as sd
        import soundfile as sf
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Install optional audio recording dependencies before recording: "
            "pip install -r requirements.txt"
        ) from exc

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    frames = int(round(duration_sec * sample_rate))
    audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
    sd.wait()
    sf.write(str(path), audio, sample_rate)
    return str(path)
