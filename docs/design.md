# Design and acceptance

User: an editor with captions on a source timeline and an ordered list of kept clips.
Acceptance: each output instant displays the cues active at the corresponding source
instant, retaining complete cue text, while removed source ranges contribute no time.

For source cue `[a,b)`, clip `[c,d)` and concatenated offset `o`, intersect at
`s=max(a,c)`, `e=min(b,d)`. If `s<e`, emit `[o+s-c, o+e-c)` with the original text.
Then increment `o` by `d-c`. This allows overlapping source cues and repeated/reordered
clips. It uses integer milliseconds throughout. No floating-point rounding or timing
inference occurs. Equal output starts are ordered by end, source ordinal, then clip.

The [Library of Congress SRT description](https://www.loc.gov/preservation/digital/formats/fdd/fdd000569.shtml)
is the format reference. SRT has variants; unsupported timing suffixes/formats fail
explicitly. Cue text is opaque and is never interpreted as HTML or commands. Unicode,
inline markup and multiline text are retained, while line endings are normalized.
The edit-list JSON parser rejects duplicate decoded keys before validation.

`core.py` handles bounded input, validation, interval mapping, receipt generation and
new-directory output. `cli.py` handles arguments and concise diagnostics. Input errors
do not contain the raw offending caption or JSON value. OS errors may contain a local
path. The JSON receipt stores timings and hashes but no source text or source paths.

Resource bounds limit both the pairwise work and the resulting memory/output growth.
The conservative byte estimate counts each emitted caption's UTF-8 length plus 64 bytes,
which exceeds supported SRT numbering and timing overhead. A receipt can still be larger
than the SRT because every dropped cue and fragment is traced; its entry count is bounded.

Output is deliberately a newly created directory. An incomplete write is retained for
inspection, never reported as success, and never automatically deleted. This is not a
sandbox against hostile concurrent filesystem changes.

Verification includes a hand-authored end-to-end example and 30 deterministic randomized
timelines checked point by point against an independent source-activity oracle. Regression
tests cover half-open boundaries, reordered/repeated clips, multilingual captions,
overlapping/unsorted cues, zero-output edits, duplicate keys, types, limits and no overwrite.
