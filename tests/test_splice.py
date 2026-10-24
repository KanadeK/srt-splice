import hashlib
import json
import random
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from srt_splice.core import (
    InputError,
    parse_clips,
    parse_srt,
    read_bounded,
    remap,
    timestamp,
    write_bundle,
)


def source(*intervals):
    return "".join(
        f"{i}\n{timestamp(start)} --> {timestamp(end)}\ncaption-{i}\n\n"
        for i, (start, end) in enumerate(intervals, 1)
    ).encode("utf-8")


def edits(*intervals):
    return json.dumps(
        {
            "schema_version": 1,
            "clips": [{"start_ms": start, "end_ms": end} for start, end in intervals],
        }
    ).encode("utf-8")


class InputTests(unittest.TestCase):
    def test_bom_crlf_and_multiline_unicode(self):
        data = "\ufeff7\r\n00:00:00,001 --> 00:00:02,009\r\n你好\r\n<i>Hello</i>\r\n".encode()
        cue = parse_srt(data)[0]
        self.assertEqual((cue.label, cue.start, cue.end), ("7", 1, 2009))
        self.assertEqual(cue.text, "你好\n<i>Hello</i>")

    def test_duplicate_counters_use_ordinals(self):
        data = source((1000, 2000), (0, 1000)).replace(b"2\n", b"1\n")
        cues = parse_srt(data)
        self.assertEqual([c.ordinal for c in cues], [1, 2])
        self.assertEqual([c.label for c in cues], ["1", "1"])

    def test_multiple_blank_separators(self):
        self.assertEqual(
            len(parse_srt(source((0, 100), (200, 300)).replace(b"\n\n", b"\n\n \n\n"))), 2
        )

    def test_invalid_srt_structure(self):
        for data in (
            b"",
            b"hello",
            b"0\n00:00:00,000 --> 00:00:01,000\na",
            b"1\n00:00:00,000 --> 00:00:01,000\n",
        ):
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_srt(data)

    def test_invalid_timestamps_and_extensions(self):
        for timing in (
            "00:61:00,000 --> 00:62:00,000",
            "00:00:01,000 --> 00:00:00,000",
            "00:00:01,000 --> 00:00:01,000",
            "00:00:00.000 --> 00:00:01.000",
            "00:00:00,000 --> 00:00:01,000 X1:10",
        ):
            with self.subTest(timing=timing), self.assertRaises(InputError):
                parse_srt(f"1\n{timing}\na".encode())

    def test_encoding_and_nul(self):
        for data in (b"\xff", b"\0"):
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_srt(data)

    def test_srt_resource_limits(self):
        with patch("srt_splice.core.MAX_CUES", 1), self.assertRaises(InputError):
            parse_srt(source((0, 1), (2, 3)))
        with patch("srt_splice.core.MAX_BYTES", 5), self.assertRaises(InputError):
            parse_srt(source((0, 1)))

    def test_read_limit(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch) / "large.srt"
            path.write_bytes(b"123456")
            with patch("srt_splice.core.MAX_BYTES", 5), self.assertRaises(InputError):
                read_bounded(path)

    def test_duplicate_json_keys_including_escapes(self):
        for data in (
            b'{"schema_version":1,"schema_version":1,"clips":[]}',
            b'{"schema_version":1,"clips":[{"start_ms":0,"start_\\u006ds":1,"end_ms":2}]}',
        ):
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_clips(data)

    def test_json_types_bounds_and_unknown_fields(self):
        bad = [
            b"null",
            b"[]",
            b"{",
            b"{}",
            b'{"schema_version":true,"clips":[]}',
            b'{"schema_version":1,"clips":[],"extra":0}',
        ]
        for start, end in ((True, 10), (0, 1.5), (-1, 10), (1, 1), (20, 10), (0, 360000000)):
            bad.append(edits((start, end)))
        for data in bad:
            with self.subTest(data=data), self.assertRaises(InputError):
                parse_clips(data)

    def test_clip_count_and_output_duration(self):
        with self.assertRaises(InputError):
            parse_clips(edits())
        with patch("srt_splice.core.MAX_CLIPS", 1), self.assertRaises(InputError):
            parse_clips(edits((0, 1), (1, 2)))
        with self.assertRaises(InputError):
            parse_clips(edits((0, 359999999), (0, 1)))


class MappingTests(unittest.TestCase):
    def test_identity_and_hashes(self):
        data, spec = source((1000, 2000), (3000, 4000)), edits((0, 5000))
        output, receipt = remap(data, spec)
        self.assertEqual(output.encode(), data)
        self.assertEqual(receipt["input_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt["edits_sha256"], hashlib.sha256(spec).hexdigest())
        self.assertEqual(receipt["output_sha256"], hashlib.sha256(data).hexdigest())

    def test_removed_gap_splits_caption(self):
        output, report = remap(source((3000, 8000)), edits((1000, 5000), (7000, 11000)))
        cues = parse_srt(output.encode())
        self.assertEqual([(c.start, c.end) for c in cues], [(2000, 4000), (4000, 5000)])
        self.assertEqual(report["summary"]["multi_fragment_cues"], 1)
        self.assertEqual(report["summary"]["clipped_cues"], 1)

    def test_reorder_and_repeat_clips(self):
        output, report = remap(
            source((0, 1000), (2000, 3000)), edits((2000, 3000), (0, 1000), (2000, 3000))
        )
        cues = parse_srt(output.encode())
        self.assertEqual([c.text for c in cues], ["caption-2", "caption-1", "caption-2"])
        self.assertEqual([(c.start, c.end) for c in cues], [(0, 1000), (1000, 2000), (2000, 3000)])
        self.assertEqual(report["summary"]["duration_ms"], 3000)

    def test_half_open_boundary_and_all_dropped(self):
        output, report = remap(source((0, 1000), (2000, 3000)), edits((1000, 2000)))
        self.assertEqual(output, "")
        self.assertEqual(report["summary"]["dropped_cues"], 2)
        self.assertEqual(report["summary"]["output_cues"], 0)

    def test_unsorted_and_overlapping_captions(self):
        output, _ = remap(source((1000, 3000), (0, 2000), (1000, 2000)), edits((0, 4000)))
        cues = parse_srt(output.encode())
        self.assertEqual([c.text for c in cues], ["caption-2", "caption-3", "caption-1"])

    def test_text_is_preserved_but_absent_from_receipt(self):
        data = source((0, 1000)).replace(b"caption-1", b"private text <b>hello</b>")
        output, report = remap(data, edits((0, 500)))
        self.assertIn("private text <b>hello</b>", output)
        self.assertNotIn("private text", json.dumps(report))
        self.assertTrue(report["cues"][0]["fragments"][0]["clipped"])

    def test_pair_and_fragment_limits_fail_explicitly(self):
        with patch("srt_splice.core.MAX_PAIRS", 1), self.assertRaises(InputError):
            remap(source((0, 1)), edits((0, 1), (0, 1)))
        with patch("srt_splice.core.MAX_FRAGMENTS", 1), self.assertRaises(InputError):
            remap(source((0, 1)), edits((0, 1), (0, 1)))
        with patch("srt_splice.core.MAX_OUTPUT_BYTES", 1), self.assertRaises(InputError):
            remap(source((0, 1)), edits((0, 1)))

    def test_randomized_timeline_matches_source_activity(self):
        rng = random.Random(3809)
        for _ in range(30):
            spans = [(a, a + rng.randint(1, 10)) for a in [rng.randint(0, 25) for _ in range(6)]]
            cuts = [(a, a + rng.randint(1, 10)) for a in [rng.randint(0, 25) for _ in range(4)]]
            output, _ = remap(source(*spans), edits(*cuts))
            mapped = parse_srt(output.encode()) if output else []
            offset = 0
            for start, end in cuts:
                for moment in range(start, end):
                    expected = sorted(
                        f"caption-{i}" for i, (a, b) in enumerate(spans, 1) if a <= moment < b
                    )
                    actual = sorted(
                        c.text for c in mapped if c.start <= offset + moment - start < c.end
                    )
                    self.assertEqual(actual, expected)
                offset += end - start


class WorkflowTests(unittest.TestCase):
    def test_bundle_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as scratch:
            output, report = remap(source((0, 1)), edits((0, 1)))
            destination = Path(scratch) / "result"
            write_bundle(destination, output, report)
            self.assertEqual((destination / "output.srt").read_text(), output)
            with self.assertRaises(FileExistsError):
                write_bundle(destination, "replacement", {})
            self.assertEqual((destination / "output.srt").read_text(), output)

    def run_cli(self, *arguments):
        return subprocess.run(
            [sys.executable, "-m", "srt_splice", *map(str, arguments)],
            text=True,
            capture_output=True,
            timeout=10,
        )

    def test_cli_dry_run(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)
            (path / "a.srt").write_bytes(source((0, 100)))
            (path / "e.json").write_bytes(edits((0, 100)))
            result = self.run_cli(path / "a.srt", path / "e.json", "--dry-run")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)["output_cues"], 1)
            self.assertEqual(len(list(path.iterdir())), 2)

    def test_cli_write_then_refuse_existing(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)
            (path / "a.srt").write_bytes(source((0, 100)))
            (path / "e.json").write_bytes(edits((0, 100)))
            args = (path / "a.srt", path / "e.json", "--out", path / "out")
            self.assertEqual(self.run_cli(*args).returncode, 0)
            self.assertEqual(self.run_cli(*args).returncode, 2)
            report = json.loads((path / "out" / "receipt.json").read_text())
            self.assertEqual(report["summary"]["output_cues"], 1)

    def test_cli_invalid_input_writes_nothing(self):
        with tempfile.TemporaryDirectory() as scratch:
            path = Path(scratch)
            (path / "bad.srt").write_text("bad")
            (path / "e.json").write_bytes(edits((0, 100)))
            result = self.run_cli(path / "bad.srt", path / "e.json", "--out", path / "out")
            self.assertEqual(result.returncode, 2)
            self.assertNotIn("Traceback", result.stderr)
            self.assertFalse((path / "out").exists())


if __name__ == "__main__":
    unittest.main()
