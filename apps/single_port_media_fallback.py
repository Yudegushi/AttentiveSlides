"""Launch the browser media fallback using only one SSH-forwarded HTTP port."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from modules.media.single_port_transport import run_single_port_server


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the AttentiveSlides single-port browser media probe."
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8501, type=int)
    arguments = parser.parse_args()
    run_single_port_server(host=arguments.host, port=arguments.port)


if __name__ == "__main__":
    main()
