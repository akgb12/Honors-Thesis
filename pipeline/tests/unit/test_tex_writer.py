from a11y_pipeline.adapters.tex_beamer.writer import (
    _escape_alt,
    _merge_hypersetup,
    _tikz_alt_comment,
    _update_includegraphics,
)


def test_writer_merges_metadata_and_escapes_image_alt() -> None:
    # Preserve unrelated settings and replace required source values
    merged = _merge_hypersetup(
        "colorlinks=true, pdftitle={Old, title}, pdflang={fr}",
        "pdftitle={New title}",
        "pdflang={en-US}",
    )
    escaped = _escape_alt("Rate {x} is 50% #1")
    updated = _update_includegraphics(
        r"\includegraphics[width={0.5\textwidth},alt={old}]{figure}",
        escaped,
    )

    assert merged == "colorlinks=true, pdftitle={New title}, pdflang={en-US}"
    assert updated == (
        r"\includegraphics[width={0.5\textwidth},alt={Rate \{x\} is 50\% \#1}]{figure}"
    )


def test_tikz_comment_wraps_every_line_to_one_hundred_columns() -> None:
    # Wrap long TikZ descriptions with the required prefix
    source = "  \\begin{tikzpicture}\n  \\end{tikzpicture}\n"
    description = (
        "A deliberately long accessible description that needs wrapping before it reaches "
        "the one hundred character source limit for generated annotation lines."
    )
    insertion = _tikz_alt_comment(source, 2, description)

    updated = source[:2] + insertion + source[2:]
    lines = updated.splitlines()
    assert len(lines) >= 2
    for line in lines:
        if not line.lstrip().startswith("% a11y-alt:"):
            continue
        assert len(line) <= 100
        assert line.lstrip().startswith("% a11y-alt:")
