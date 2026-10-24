# Release verification

Version 0.1.0 was verified locally with CPython 3.13.16 on Windows.

- 23 regression tests pass, including actual CLI writes/dry runs and refusal to overwrite
  an existing directory. Invalid input creates no output directory.
- The timeline property test checks 30 seeded randomized cases at every integer instant
  against an independent source-activity oracle. It includes unsorted overlapping cues,
  reordered clips and repetitions.
- The complete example checks manually specified output SRT times/text and receipt counts.
- Ruff lint/format checks and sdist/wheel builds pass. Runtime dependencies are empty.
- The built wheel is installed without dependencies in a fresh environment outside the
  checkout, where the regression suite and documented acceptance example are rerun.
- Release requires the four Ubuntu/Windows × Python 3.11/3.13 CI jobs to pass.

Second-pass review found and addressed output-growth risk: a bound on comparisons alone
does not limit repeated caption text. Separate fragment and conservative byte budgets now
fail explicitly before result construction. Review also checked half-open boundaries,
exact integer offsets, duplicate JSON keys, Unicode preservation, timing-only receipts,
new-directory semantics, and honest treatment of clipped words and video-cut rounding.

These are timing-transform checks. No media playback, speech alignment or accessibility
certification is claimed.
