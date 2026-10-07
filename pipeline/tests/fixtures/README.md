# Test fixtures

Copy this whole folder to `pipeline/tests/fixtures/` in M0 and commit it there (it is test
data, not onboarding material). Do not edit the originals inside tests; copy to a temp dir
when a test needs to modify a project (e.g. delete `figs/`).

## `adversarial/` — parser only (does not compile on purpose)

`deck.tex` stresses the parser: commented-out frame, `\%` and `\$` escapes, trailing
comment, `\item<2->`, nested `itemize`/`enumerate`, both frame-title forms, `[fragile]`,
inline + display math, `\pause`, `\includegraphics` of a missing file, TikZ with a brace
inside a comment, a user-defined macro. Golden output: `expected_elements.txt`.

## `lecture_sample/` — the end-to-end fixture (compiles; 10 PDF pages)

`main.tex` + `figs/regression.png`. Madrid theme. Six frames:

| Frame | Pages | What it exercises |
|---|---|---|
| 1 title page | 1 | metadata (title, subtitle, author, institute, date) → H1 + P |
| 2 Course Logistics | 2–3 | list, `\item<2->` overlays, nested enumerate, `\%` `\$` |
| 3 Linear Models | 4–5 | paragraph with inline math, `\pause`, display math, raster figure |
| 4 Cross-Validation | 6–7 | list with inline math, `\pause`, TikZ figure whose "Test" box hides the "Fold 3" label, caption sentence |
| 5 Overlays That Replace Content | 8–9 | `\only<1>` / `\only<2>`: each paragraph exists on one page only |
| 6 A Custom Macro | 10 | user macro `\myplot` → `unknown`, `not_handled`, left unmarked |

Verified facts you can assert in tests (see `../reference/VERIFIED_FINDINGS.md`):
- original and marked compiles both have 10 pages and are pixel-identical;
- the TikZ figure (`slide_04/figure_01`) is present on pages 6 and 7 (hidden on 6 by the
  overlay), so it is tagged on page 7 and its page-6 marker becomes an artifact;
- `slide_05/paragraph_01` exists only on page 8, `slide_05/paragraph_02` only on page 9;
- after tagging, 24 marked-content sequences are linked, no broken links, and the only
  unmarked text on any page is `\myplot`'s output on page 10;
- hidden-label detection finds "3" (of "Fold 3") hidden on page 7.

Variant for the missing-image tests: copy `lecture_sample/` to a temp dir and delete `figs/`.
Expected: pre-flight warns (runnable), `slide_03/figure_01` becomes `missing_asset`, only one
model task remains (the TikZ figure).

Fake-model script for the repair demo (`--seed-weak slide_04/figure_01`): round 0 uses the
weak text "Five boxes in a row, one is blue."; the capability then returns
"Five-fold cross-validation: a row of five folds where the third position is the test fold."
