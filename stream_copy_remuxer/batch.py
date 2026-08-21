from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable

from .engine import RemuxCancelled, RemuxEngine
from .encoding import COPY_PROFILE_KEY, effective_container_key, profile_for
from .models import CONTAINER_PROFILES, MediaProbe, ProgressUpdate, RemuxPlan, RemuxResult, Toolchain
from .planning import PlanError, suggest_output


STATE_INSPECTING = "inspecting"
STATE_READY = "ready"
STATE_QUEUED = "queued"
STATE_PROCESSING = "processing"
STATE_COMPLETE = "complete"
STATE_FAILED = "failed"
STATE_CANCELED = "canceled"
STATE_INVALID = "invalid"


@dataclass
class BatchItem:
    item_id: str
    source: Path
    container_key: str = "mp4"
    video_encoding_key: str = COPY_PROFILE_KEY
    quality_value: int | None = None
    media: MediaProbe | None = None
    output: Path | None = None
    state: str = STATE_INSPECTING
    detail: str = "Inspecting…"
    result: RemuxResult | None = None

    @property
    def can_run(self) -> bool:
        return self.media is not None and self.state in {
            STATE_READY,
            STATE_FAILED,
            STATE_CANCELED,
        }


@dataclass(frozen=True)
class BatchSpaceRequirement:
    volume: str
    available_bytes: int
    required_bytes: int
    item_count: int


@dataclass(frozen=True)
class BatchExecutionSummary:
    completed: int
    failed: int
    canceled: bool
    total: int
    results: tuple[RemuxResult, ...]
    failures: tuple[tuple[str, str], ...]


def normalized_path_key(path: Path) -> str:
    try:
        resolved = Path(path).expanduser().resolve(strict=False)
    except OSError:
        resolved = Path(os.path.abspath(str(Path(path).expanduser())))
    return os.path.normcase(str(resolved))


def unique_existing_files(
    candidates: Iterable[Path],
    *,
    existing_paths: Iterable[Path] = (),
) -> tuple[tuple[Path, ...], tuple[Path, ...], tuple[Path, ...]]:
    seen = {normalized_path_key(path) for path in existing_paths}
    accepted: list[Path] = []
    duplicates: list[Path] = []
    rejected: list[Path] = []
    for candidate in candidates:
        try:
            path = Path(candidate).expanduser().resolve(strict=False)
        except OSError:
            path = Path(candidate).expanduser().absolute()
        if not path.is_file():
            rejected.append(path)
            continue
        key = normalized_path_key(path)
        if key in seen:
            duplicates.append(path)
            continue
        seen.add(key)
        accepted.append(path)
    return tuple(accepted), tuple(duplicates), tuple(rejected)


def allocate_output_paths(
    items: Iterable[BatchItem],
    *,
    output_directory: Path | None = None,
    locked_outputs: Iterable[Path] = (),
) -> dict[str, Path]:
    destination: Path | None = None
    if output_directory is not None:
        destination = Path(output_directory).expanduser().resolve(strict=False)
        if not destination.is_dir():
            raise PlanError(f"The destination folder does not exist: {destination}")
    reserved = list(locked_outputs)
    allocated: dict[str, Path] = {}
    for item in items:
        expected_container = effective_container_key(item.video_encoding_key, item.container_key)
        if item.container_key not in CONTAINER_PROFILES:
            raise PlanError(f"Unsupported destination container: {item.container_key}")
        if expected_container != item.container_key:
            raise PlanError(
                f"{profile_for(item.video_encoding_key).label} requires "
                f"{CONTAINER_PROFILES[expected_container].label} output."
            )
        output = suggest_output(
            item.source,
            item.container_key,
            video_encoding_key=item.video_encoding_key,
            output_directory=destination,
            reserved_paths=reserved,
        )
        allocated[item.item_id] = output
        reserved.append(output)
    return allocated


def input_container_summary(media: MediaProbe) -> str:
    suffix = media.path.suffix.lstrip(".").upper()
    detected = media.format_long_name.strip() or media.format_name.strip() or "Unknown container"
    return f"{detected} ({suffix})" if suffix else detected


def codec_summary(media: MediaProbe, codec_type: str) -> str:
    codecs: list[str] = []
    for stream in media.streams:
        if stream.codec_type != codec_type:
            continue
        label = (stream.codec_name or "unknown").upper()
        if label not in codecs:
            codecs.append(label)
    return ", ".join(codecs) if codecs else "—"


def _volume_key(path: Path) -> tuple[int | None, str]:
    try:
        device = path.stat().st_dev
    except OSError:
        device = None
    anchor = os.path.normcase(str(path.resolve(strict=False).anchor))
    return device, anchor


def ensure_batch_space(plans: Iterable[RemuxPlan]) -> tuple[BatchSpaceRequirement, ...]:
    groups: dict[tuple[int | None, str], list[RemuxPlan]] = {}
    for plan in plans:
        groups.setdefault(_volume_key(plan.output.parent), []).append(plan)

    requirements: list[BatchSpaceRequirement] = []
    for (_device, anchor), grouped_plans in groups.items():
        estimated_output_bytes = sum(
            plan.estimated_output_bytes or plan.source_probe.size for plan in grouped_plans
        )
        reserve = max(256 * 1024 * 1024, estimated_output_bytes // 100)
        required = estimated_output_bytes + reserve
        available = shutil.disk_usage(grouped_plans[0].output.parent).free
        volume = anchor or str(grouped_plans[0].output.parent)
        requirement = BatchSpaceRequirement(
            volume=volume,
            available_bytes=available,
            required_bytes=required,
            item_count=len(grouped_plans),
        )
        requirements.append(requirement)
        if available < required:
            raise PlanError(
                "The destination does not have enough free space for this batch. "
                f"Volume {volume or '(unknown)'} requires approximately {required:,} bytes "
                f"for {len(grouped_plans)} output(s); {available:,} bytes are available."
            )
    return tuple(requirements)


def run_batch_plans(
    toolchain: Toolchain,
    plan_records: Iterable[tuple[str, RemuxPlan]],
    *,
    cancel_event: object,
    on_item_starting: Callable[[str, int, int], None] | None = None,
    on_item_finished: Callable[[str, RemuxResult | None, Exception | None], None] | None = None,
    on_status: Callable[[str, int, int, str], None] | None = None,
    on_progress: Callable[[str, int, int, ProgressUpdate], None] | None = None,
    on_log: Callable[[str, str], None] | None = None,
    engine_factory: Callable[[Toolchain], RemuxEngine] = RemuxEngine,
) -> BatchExecutionSummary:
    """Run immutable batch plans sequentially, continuing after per-file failures."""
    records = tuple(plan_records)
    total = len(records)
    completed = 0
    failed = 0
    canceled = False
    results: list[RemuxResult] = []
    failures: list[tuple[str, str]] = []

    is_set = getattr(cancel_event, "is_set", None)
    if not callable(is_set):
        raise TypeError("cancel_event must provide is_set().")

    for index, (item_id, plan) in enumerate(records, start=1):
        if is_set():
            canceled = True
            break
        if on_item_starting is not None:
            on_item_starting(item_id, index, total)
        try:
            result = engine_factory(toolchain).run(
                plan,
                cancel_event=cancel_event,
                on_status=(
                    (lambda text, iid=item_id, number=index: on_status(iid, number, total, text))
                    if on_status is not None
                    else None
                ),
                on_progress=(
                    (lambda update, iid=item_id, number=index: on_progress(iid, number, total, update))
                    if on_progress is not None
                    else None
                ),
                on_log=(
                    (lambda text, iid=item_id: on_log(iid, text))
                    if on_log is not None
                    else None
                ),
            )
        except RemuxCancelled as exc:
            canceled = True
            if on_item_finished is not None:
                on_item_finished(item_id, None, exc)
            break
        except Exception as exc:
            failed += 1
            failures.append((item_id, str(exc)))
            if on_item_finished is not None:
                on_item_finished(item_id, None, exc)
        else:
            completed += 1
            results.append(result)
            if on_item_finished is not None:
                on_item_finished(item_id, result, None)

    return BatchExecutionSummary(
        completed=completed,
        failed=failed,
        canceled=canceled,
        total=total,
        results=tuple(results),
        failures=tuple(failures),
    )
