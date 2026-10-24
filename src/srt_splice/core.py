"""Strict SRT parsing and exact integer interval remapping."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

MAX_BYTES = 8 * 1024 * 1024
MAX_CUES = 100000
MAX_CLIPS = 1000
MAX_PAIRS = 5000000
MAX_FRAGMENTS = 100000
MAX_OUTPUT_BYTES = 32 * 1024 * 1024
MAX_TIME = 359999999  # 99:59:59,999, the supported two-digit-hour SRT range.
STAMP = r"([0-9]{2}):([0-5][0-9]):([0-5][0-9]),([0-9]{3})"
TIMELINE = re.compile(STAMP + r"[ \t]+-->[ \t]+" + STAMP)


class InputError(ValueError):
    """An input is outside the explicit supported format or resource bounds."""


@dataclass(frozen=True)
class Cue:
    ordinal: int
    label: str
    start: int
    end: int
    text: str


@dataclass(frozen=True)
class Clip:
    start: int
    end: int


def _millis(parts) -> int:
    hours, minutes, seconds, milliseconds = map(int, parts)
    return ((hours * 60 + minutes) * 60 + seconds) * 1000 + milliseconds


def timestamp(value: int) -> str:
    hours, rest = divmod(value, 3600000)
    minutes, rest = divmod(rest, 60000)
    seconds, milliseconds = divmod(rest, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def read_bounded(path: Path) -> bytes:
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise InputError(f"input exceeds {MAX_BYTES} bytes")
    return data


def _decode(data: bytes) -> str:
    if len(data) > MAX_BYTES:
        raise InputError(f"input exceeds {MAX_BYTES} bytes")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise InputError("input must be UTF-8 (an initial BOM is allowed)") from error
    if "\0" in text:
        raise InputError("NUL is not supported in text input")
    return text


def parse_srt(data: bytes) -> list[Cue]:
    text = _decode(data).replace("\r\n", "\n").replace("\r", "\n").strip("\n")
    cues = []
    for block in re.split(r"\n(?:[ \t]*\n)+", text):
        if not block.strip():
            continue
        ordinal = len(cues) + 1
        lines = block.split("\n")
        if len(lines) < 3 or not re.fullmatch(r"[0-9]{1,9}", lines[0].strip()):
            raise InputError(f"cue {ordinal}: expected numeric counter, timing and text")
        label = lines[0].strip()
        if int(label) < 1:
            raise InputError(f"cue {ordinal}: counter must be positive")
        match = TIMELINE.fullmatch(lines[1].strip())
        if not match:
            raise InputError(f"cue {ordinal}: expected HH:MM:SS,mmm --> HH:MM:SS,mmm")
        start, end = _millis(match.groups()[:4]), _millis(match.groups()[4:])
        if start >= end:
            raise InputError(f"cue {ordinal}: end must be greater than start")
        caption = "\n".join(lines[2:])
        if not caption.strip():
            raise InputError(f"cue {ordinal}: text is empty")
        cues.append(Cue(ordinal, label, start, end, caption))
        if len(cues) > MAX_CUES:
            raise InputError(f"more than {MAX_CUES} cues")
    if not cues:
        raise InputError("no SRT cues found")
    return cues


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate JSON object key")
        result[key] = value
    return result


def parse_clips(data: bytes) -> list[Clip]:
    try:
        value = json.loads(_decode(data), object_pairs_hook=_unique_object)
    except (json.JSONDecodeError, RecursionError) as error:
        raise InputError("edit list must be valid JSON") from error
    if not isinstance(value, dict) or set(value) != {"schema_version", "clips"}:
        raise InputError("edit list requires exactly schema_version and clips")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise InputError("schema_version must be the integer 1")
    items = value["clips"]
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_CLIPS:
        raise InputError(f"clips must contain 1..{MAX_CLIPS} items")
    clips = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict) or set(item) != {"start_ms", "end_ms"}:
            raise InputError(f"clip {index}: requires exactly start_ms and end_ms")
        start, end = item["start_ms"], item["end_ms"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= MAX_TIME:
            raise InputError(
                f"clip {index}: integer bounds must satisfy 0 <= start < end <= {MAX_TIME}"
            )
        clips.append(Clip(start, end))
    if sum(clip.end - clip.start for clip in clips) > MAX_TIME:
        raise InputError("concatenated duration exceeds 99:59:59,999")
    return clips


def remap(srt_data: bytes, edits_data: bytes) -> tuple[str, dict]:
    cues, clips = parse_srt(srt_data), parse_clips(edits_data)
    if len(cues) * len(clips) > MAX_PAIRS:
        raise InputError(f"cue/clip comparison budget exceeds {MAX_PAIRS}")
    fragments = []
    text_bytes = {cue.ordinal: len(cue.text.encode("utf-8")) for cue in cues}
    estimated_output_bytes = 0
    offset = 0
    for clip_index, clip in enumerate(clips, 1):
        for cue in cues:
            start, end = max(clip.start, cue.start), min(clip.end, cue.end)
            if start < end:
                estimated_output_bytes += text_bytes[cue.ordinal] + 64
                if len(fragments) >= MAX_FRAGMENTS or estimated_output_bytes > MAX_OUTPUT_BYTES:
                    raise InputError("output fragment/byte budget exceeded; split the edit list")
                fragments.append(
                    {
                        "clip": clip_index,
                        "source_ordinal": cue.ordinal,
                        "source_ms": [start, end],
                        "output_ms": [offset + start - clip.start, offset + end - clip.start],
                        "clipped": start != cue.start or end != cue.end,
                    }
                )
        offset += clip.end - clip.start
    fragments.sort(key=lambda f: (*f["output_ms"], f["source_ordinal"], f["clip"]))
    outputs = []
    by_cue = {cue.ordinal: [] for cue in cues}
    for index, fragment in enumerate(fragments, 1):
        fragment["output_ordinal"] = index
        by_cue[fragment["source_ordinal"]].append(fragment)
        cue = cues[fragment["source_ordinal"] - 1]
        start, end = fragment["output_ms"]
        outputs.append(f"{index}\n{timestamp(start)} --> {timestamp(end)}\n{cue.text}\n\n")
    output = "".join(outputs)
    receipt = {
        "schema_version": 1,
        "input_sha256": hashlib.sha256(srt_data).hexdigest(),
        "edits_sha256": hashlib.sha256(edits_data).hexdigest(),
        "output_sha256": hashlib.sha256(output.encode("utf-8")).hexdigest(),
        "summary": {
            "input_cues": len(cues),
            "output_cues": len(fragments),
            "clips": len(clips),
            "duration_ms": offset,
            "dropped_cues": sum(not by_cue[cue.ordinal] for cue in cues),
            "clipped_cues": sum(any(f["clipped"] for f in by_cue[cue.ordinal]) for cue in cues),
            "multi_fragment_cues": sum(len(by_cue[cue.ordinal]) > 1 for cue in cues),
        },
        "cues": [
            {
                "source_ordinal": cue.ordinal,
                "original_counter": cue.label,
                "source_ms": [cue.start, cue.end],
                "fragments": by_cue[cue.ordinal],
            }
            for cue in cues
        ],
    }
    return output, receipt


def write_bundle(destination: Path, output: str, receipt: dict) -> None:
    """A new directory only; errors retain partial output for explicit user cleanup."""
    destination.mkdir(mode=0o700, parents=False, exist_ok=False)
    with (destination / "output.srt").open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(output)
    # Receipt is written last. A failed write is never reported as success.
    with (destination / "receipt.json").open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(receipt, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
