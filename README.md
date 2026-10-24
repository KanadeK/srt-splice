# srt-splice

Make existing captions follow your video cuts. Supply a UTF-8 SRT and an ordered list of
source intervals; get a new SRT and a receipt tracing every original cue to its output
fragments. Clips may be reordered or repeated. Everything runs locally with Python 3.11+
and no runtime dependencies.

[中文说明](README.zh-CN.md) · [Input and algorithm](docs/design.md) · [MIT](LICENSE)

## Install and try a complete example

```sh
git clone https://github.com/KanadeK/srt-splice.git
cd srt-splice
python -m pip install .
srt-splice examples/source.srt examples/edits.json --dry-run
srt-splice examples/source.srt examples/edits.json --out work-output
python examples/check_example.py
```

The example retains seconds 1–5 and 7–11, producing an eight-second caption track.
One original cue appears across both clips and one is dropped. The acceptance script
compares the generated timestamps and text with the manually authored
[`expected.srt`](examples/expected.srt), and checks the receipt counts.

```json
{"input_cues":4,"output_cues":4,"clips":2,"duration_ms":8000,"dropped_cues":1,"clipped_cues":2,"multi_fragment_cues":1}
```

`work-output` must not exist; its parent must exist. It contains `output.srt` and
`receipt.json`. Reusing an existing directory is an error. Use another new directory
for another run. `--dry-run` performs the same validation/remapping and only prints
the summary. `python -m srt_splice` is equivalent to the console command.

## Describe the edit

```json
{
  "schema_version": 1,
  "clips": [
    {"start_ms": 1000, "end_ms": 5000},
    {"start_ms": 7000, "end_ms": 11000}
  ]
}
```

Times are exact integer milliseconds on the original source timeline. Intervals are
half-open `[start_ms, end_ms)` and concatenate in array order, without gaps between
clips. Repeated or overlapping source intervals intentionally repeat content. To add
silence/gaps, include the corresponding source interval; generated gaps are not supported.
Supply the actual edit times used by your video tool, including any keyframe rounding.

Each cue is intersected with each retained interval and shifted by the total duration
of earlier clips. Empty intersections are dropped; positive intersections retain the
whole cue text. Output cues are sorted by time and renumbered. Text and inline markup
are preserved; line endings become LF. Duplicate source counters and overlapping or
unsorted cues are accepted, with one-based source **ordinals** providing unambiguous
receipt references.

The receipt contains input/edit/output SHA-256 values, counts, original counters,
source intervals, clip numbers, output cue numbers, and clipped fragments. It does not
include caption text or input paths. `multi_fragment_cues` includes repeated clips as
well as cuts through a cue. A valid edit may remove every cue; that succeeds with an
empty SRT and an explicit dropped count.

## Where it fits

Editors cutting lectures or interviews often have captions aligned to the full source.
[LosslessCut's discussion](https://github.com/mifi/lossless-cut/discussions/1965) illustrates
the friction of trimming external captions. Full editors such as
[Subtitle Edit](https://github.com/SubtitleEdit/subtitleedit), video-splitting tools such as
[cut-video-with-subs](https://github.com/abdnh/cut-video-with-subs), and
[ytclip's remapping workflow](https://github.com/billietomato/ytclip) are alternatives.
This utility focuses on a documented, deterministic edit-list transform with cue-level
receipts and no video, NLE, model, or service dependency. Its implementation and examples
are original.

## Limits and privacy

Version 0.1.0 supports strict SRT with positive numeric counters, two-digit hours,
comma milliseconds, and nonempty text. UTF-8 BOM, CRLF/LF/CR line endings and multiline
Unicode text work. WebVTT/ASS, coordinate suffixes, speed changes, transitions, frame
rate conversion, NLE project import, ASR and translation are outside scope.

Clipping a cue preserves **all of its words** in each fragment; it cannot know which
words were spoken before a cut. Review clipped and multi-fragment cues before publishing.
No video is read, so audio/video synchronization or accessibility quality is not certified.

Each input is limited to 8 MiB; at most 100,000 cues, 1,000 clips, 5,000,000 cue/clip
comparisons and 100,000 output fragments are supported. The conservative output byte
estimate (caption UTF-8 bytes + 64 per fragment) is capped at 32 MiB. The output timeline
must fit `99:59:59,999`. Exceeding a limit is an error, never a partial successful result.
Processing and the full receipt use memory proportional to cues/fragments. Duplicate
JSON keys and unknown manifest fields are rejected.

Inputs are read only. Output requires a new directory; it is created only after full
validation. Disk errors can leave an incomplete directory for inspection and explicit
cleanup; receipt writing is last. Concurrent hostile filesystem changes are outside
the safety boundary. Caption output contains the original private text; protect it as
you would the source. Timing receipts are metadata, not anonymization. No telemetry.

## Development and cleanup

```sh
python -m pip install -e . -r requirements-dev.txt
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m build
python -m pip uninstall srt-splice
```

Exit `0` means the transformation completed (including dry runs or all-dropped edits).
Exit `2` means an input, resource, argument or filesystem error. Remove your chosen
output directory when finished; no background process or hidden database is created.
See [contributing](CONTRIBUTING.md) and [security reporting](SECURITY.md).
