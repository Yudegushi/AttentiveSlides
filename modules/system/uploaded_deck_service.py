"""Runtime PDF upload and slide preparation for the Main UI."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from modules.common.schemas import AOI
from modules.slide.aoi_manager import (
    AOIManager,
)
from modules.slide.slide_parser import (
    SlideParser,
)
from modules.system.main_ui_state import (
    MainUISlide,
)


REPOSITORY_ROOT = Path(
    __file__
).resolve().parents[2]


@dataclass(frozen=True)
class UploadedDeckSummary:
    deck_id: str
    title: str
    page_count: int
    content_digest: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class UploadedDeckBrowser:
    """Deck-browser interface for an uploaded PDF."""

    def __init__(
        self,
        workspace: "UploadedDeckWorkspace",
        summary: UploadedDeckSummary,
    ) -> None:
        self.workspace = workspace
        self.deck_id = summary.deck_id
        self.title = summary.title
        self.page_count = summary.page_count
        self.content_digest = (
            summary.content_digest
        )
        self.manifest_path = (
            workspace.aoi_manager.manifest_file
        )
        self._slide_ids = tuple(
            range(
                1,
                self.page_count + 1,
            )
        )

    @property
    def slide_ids(self) -> tuple[int, ...]:
        return self._slide_ids

    def get_slide(
        self,
        slide_id: int,
    ) -> MainUISlide:
        return self.workspace.get_slide(
            self.deck_id,
            slide_id,
        )

    def slide_index(
        self,
        slide_id: int,
    ) -> int:
        try:
            return self.slide_ids.index(
                slide_id
            )
        except ValueError as exc:
            raise KeyError(
                f"Slide {slide_id} is not "
                f"in deck {self.deck_id!r}."
            ) from exc

    def previous_slide_id(
        self,
        slide_id: int,
    ) -> int | None:
        index = self.slide_index(
            slide_id
        )

        if index == 0:
            return None

        return self.slide_ids[
            index - 1
        ]

    def next_slide_id(
        self,
        slide_id: int,
    ) -> int | None:
        index = self.slide_index(
            slide_id
        )

        if index >= len(
            self.slide_ids
        ) - 1:
            return None

        return self.slide_ids[
            index + 1
        ]


def configured_pdf_render_dpi() -> int:
    """Return a bounded PDF rasterization DPI for uploaded decks."""
    raw_value = os.environ.get(
        "ATTENTIVE_PDF_RENDER_DPI",
        "220",
    )

    try:
        dpi = int(raw_value)
    except (TypeError, ValueError):
        dpi = 220

    return max(
        144,
        min(300, dpi),
    )

class UploadedDeckWorkspace:
    """Persistent runtime workspace outside the Git repository."""

    def __init__(
        self,
        data_dir: str | Path,
    ) -> None:
        self.data_dir = Path(
            data_dir
        ).resolve()

        self.data_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.incoming_dir = (
            self.data_dir
            / "incoming"
        )
        self.incoming_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.index_file = (
            self.data_dir
            / "upload_index.json"
        )

        self.slide_parser = SlideParser(
            str(self.data_dir)
        )

        self.aoi_manager = AOIManager(
            str(self.data_dir)
        )

        self.upload_index = (
            self._load_index()
        )

    def ingest_pdf(
        self,
        *,
        filename: str,
        content: bytes,
    ) -> UploadedDeckSummary:
        """Register a PDF without loading PyMuPDF in Streamlit."""
        safe_name = Path(filename).name

        if (
            not safe_name
            or Path(safe_name).suffix.lower()
            != ".pdf"
        ):
            raise ValueError(
                "Uploaded file must be a PDF."
            )

        if not content:
            raise ValueError(
                "Uploaded PDF is empty."
            )

        digest = hashlib.sha256(
            content
        ).hexdigest()

        existing_deck_id = (
            self.upload_index.get(digest)
        )

        if existing_deck_id:
            deck_info = (
                self.slide_parser.get_deck_info(
                    existing_deck_id
                )
            )

            if deck_info is not None:
                stored_path = Path(
                    str(
                        deck_info.get(
                            "pdf_path",
                            "",
                        )
                    )
                )

                if stored_path.is_file():
                    return self._summary_from_info(
                        existing_deck_id,
                        deck_info,
                        digest,
                    )

        source_path = (
            self.incoming_dir
            / f"{digest[:16]}.pdf"
        )

        source_path.write_bytes(content)

        probe = self._run_native_worker(
            [
                "probe",
                "--input-path",
                str(source_path),
            ],
            timeout_seconds=90,
        )

        page_count = int(
            probe["page_count"]
        )

        deck_id = uuid.uuid4().hex[:12]

        stored_pdf_path = (
            self.slide_parser.uploaded_dir
            / f"{deck_id}.pdf"
        )

        shutil.copy2(
            source_path,
            stored_pdf_path,
        )

        deck_info = {
            "deck_id": deck_id,
            "original_name": safe_name,
            "pdf_path": str(
                stored_pdf_path
            ),
            "page_count": page_count,
            "created_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "first_page_embedded_text_length": (
                int(
                    probe[
                        "first_page_embedded_text_length"
                    ]
                )
            ),
        }

        self.slide_parser.metadata[
            deck_id
        ] = deck_info

        self.slide_parser._save_metadata()

        self.upload_index[digest] = deck_id
        self._save_index()

        return self._summary_from_info(
            deck_id,
            deck_info,
            digest,
        )

    def open_browser(
        self,
        deck_id: str,
    ) -> UploadedDeckBrowser:
        deck_info = (
            self.slide_parser
            .get_deck_info(deck_id)
        )

        if deck_info is None:
            raise ValueError(
                f"Unknown uploaded deck: "
                f"{deck_id!r}."
            )

        digest = next(
            (
                current_digest
                for (
                    current_digest,
                    current_deck_id,
                )
                in self.upload_index.items()
                if current_deck_id
                == deck_id
            ),
            "",
        )

        summary = (
            self._summary_from_info(
                deck_id,
                deck_info,
                digest,
            )
        )

        return UploadedDeckBrowser(
            self,
            summary,
        )

    def get_slide(
        self,
        deck_id: str,
        slide_id: int,
    ) -> MainUISlide:
        page_count = (
            self.slide_parser
            .get_page_count(deck_id)
        )

        if (
            slide_id < 1
            or slide_id > page_count
        ):
            raise ValueError(
                f"slide_id out of range: "
                f"{slide_id}."
            )

        slide_data = (
            self._get_or_process_slide(
                deck_id,
                slide_id,
            )
        )

        aois = tuple(
            AOI(
                aoi_id=str(
                    item["aoi_id"]
                ),
                bbox=[
                    float(value)
                    for value
                    in item["bbox"]
                ],
                type=str(
                    item.get(
                        "type",
                        "unknown",
                    )
                ),
                text=str(
                    item.get(
                        "text",
                        "",
                    )
                ),
                name=str(
                    item.get(
                        "name",
                        item["aoi_id"],
                    )
                ),
            )
            for item in slide_data.get(
                "aois",
                [],
            )
            if item.get(
                "include_in_learning",
                True,
            )
        )

        neighbor_texts: list[str] = []

        for neighbor_id in (
            slide_id - 1,
            slide_id + 1,
        ):
            if (
                neighbor_id < 1
                or neighbor_id > page_count
            ):
                continue

            key = self._slide_key(
                deck_id,
                neighbor_id,
            )

            neighbor_data = (
                self.aoi_manager
                .manifest
                .get(key)
            )

            if neighbor_data:
                neighbor_text = str(
                    neighbor_data.get(
                        "ocr_text",
                        "",
                    )
                ).strip()

                if neighbor_text:
                    neighbor_texts.append(
                        neighbor_text
                    )

        image_path = str(
            slide_data.get(
                "slide_image_path",
                "",
            )
        ).strip()

        return MainUISlide(
            slide_id=slide_id,
            slide_text=str(
                slide_data.get(
                    "ocr_text",
                    "",
                )
            ),
            neighbor_slide_text=(
                "\n\n".join(
                    neighbor_texts
                )
            ),
            aois=aois,
            image_path=(
                image_path
                if image_path
                else None
            ),
        )

    def _get_or_process_slide(
        self,
        deck_id: str,
        slide_id: int,
    ) -> dict[str, Any]:
        render_dpi = configured_pdf_render_dpi()

        key = self._slide_key(
            deck_id,
            slide_id,
        )

        existing = (
            self.aoi_manager
            .manifest
            .get(key)
        )

        if existing is not None:
            image_path = Path(
                str(
                    existing.get(
                        "slide_image_path",
                        "",
                    )
                )
            )

            expected_suffix = (
                f"_{render_dpi}dpi.png"
            )

            if (
                image_path.is_file()
                and image_path.name.endswith(
                    expected_suffix
                )
            ):
                return existing

        worker_arguments = [
            "prepare-slide",
            "--data-dir",
            str(self.data_dir),
            "--deck-id",
            deck_id,
            "--slide-id",
            str(slide_id),
            "--dpi",
            str(render_dpi),
        ]

        if (
            os.environ.get(
                "ATTENTIVE_ENABLE_OCR",
                "0",
            )
            == "1"
        ):
            worker_arguments.append(
                "--enable-ocr"
            )

        self._run_native_worker(
            worker_arguments,
            timeout_seconds=300,
        )

        self.aoi_manager = AOIManager(
            str(self.data_dir)
        )

        processed = (
            self.aoi_manager
            .manifest
            .get(key)
        )

        if processed is None:
            raise RuntimeError(
                "PDF worker completed without "
                "creating slide data."
            )

        return processed

    def _run_native_worker(
        self,
        worker_arguments: list[str],
        *,
        timeout_seconds: int,
    ) -> dict[str, Any]:
        worker_path = (
            REPOSITORY_ROOT
            / "scripts"
            / "pdf_native_worker.py"
        )

        if not worker_path.is_file():
            raise FileNotFoundError(
                f"PDF worker not found: "
                f"{worker_path}"
            )

        result_directory = (
            self.data_dir
            / "worker_results"
        )

        result_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        descriptor, result_name = (
            tempfile.mkstemp(
                prefix="pdf_worker_",
                suffix=".json",
                dir=result_directory,
            )
        )

        os.close(descriptor)

        result_path = Path(
            result_name
        )

        command = [
            sys.executable,
            str(worker_path),
            "--output",
            str(result_path),
            *worker_arguments,
        ]

        environment = os.environ.copy()

        environment.update(
            {
                "OMP_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
                "TOKENIZERS_PARALLELISM": (
                    "false"
                ),
                "PYTHONFAULTHANDLER": "1",
            }
        )

        try:
            completed = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=environment,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                check=False,
            )

            if completed.returncode != 0:
                signal_note = (
                    f" native signal "
                    f"{-completed.returncode}"
                    if completed.returncode < 0
                    else ""
                )

                stderr_tail = (
                    completed.stderr[-4000:]
                    if completed.stderr
                    else "<empty>"
                )

                raise RuntimeError(
                    "PDF worker failed with "
                    f"return code "
                    f"{completed.returncode}"
                    f"{signal_note}.\n"
                    f"Worker stderr:\n"
                    f"{stderr_tail}"
                )

            if not result_path.is_file():
                raise RuntimeError(
                    "PDF worker produced no "
                    "result file."
                )

            payload = json.loads(
                result_path.read_text(
                    encoding="utf-8"
                )
            )

            if not payload.get("ok"):
                raise RuntimeError(
                    "PDF worker error: "
                    f"{payload.get('error_type')}: "
                    f"{payload.get('error')}"
                )

            result = payload.get(
                "result"
            )

            if not isinstance(
                result,
                dict,
            ):
                raise RuntimeError(
                    "PDF worker returned an "
                    "invalid result."
                )

            return result

        finally:
            result_path.unlink(
                missing_ok=True
            )

    def _summary_from_info(
        self,
        deck_id: str,
        deck_info: dict[str, Any],
        digest: str,
    ) -> UploadedDeckSummary:
        return UploadedDeckSummary(
            deck_id=deck_id,
            title=str(
                deck_info.get(
                    "original_name",
                    deck_id,
                )
            ),
            page_count=int(
                deck_info["page_count"]
            ),
            content_digest=digest,
        )

    def _load_index(
        self,
    ) -> dict[str, str]:
        if not self.index_file.exists():
            return {}

        payload = json.loads(
            self.index_file.read_text(
                encoding="utf-8"
            )
        )

        if not isinstance(payload, dict):
            raise ValueError(
                "upload_index.json must "
                "contain an object."
            )

        return {
            str(key): str(value)
            for key, value
            in payload.items()
        }

    def _save_index(self) -> None:
        temporary_path = (
            self.index_file
            .with_suffix(".json.tmp")
        )

        temporary_path.write_text(
            json.dumps(
                self.upload_index,
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        temporary_path.replace(
            self.index_file
        )

    @staticmethod
    def _slide_key(
        deck_id: str,
        slide_id: int,
    ) -> str:
        return (
            f"{deck_id}:{slide_id}"
        )
