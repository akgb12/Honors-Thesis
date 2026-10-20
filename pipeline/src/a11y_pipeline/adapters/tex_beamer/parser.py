import re
from bisect import bisect_right
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pylatexenc.latexwalker import (
    LatexCharsNode,
    LatexCommentNode,
    LatexEnvironmentNode,
    LatexGroupNode,
    LatexMacroNode,
    LatexMathNode,
    LatexWalker,
    get_default_latex_context_db,
)
from pylatexenc.macrospec import MacroSpec

from a11y_pipeline.adapters.tex_beamer.records import (
    NativeDocument,
    NativeRecord,
    NativeSource,
)
from a11y_pipeline.bundle.bundle import Bundle

ESCAPE_MACROS = {"%": "%", "$": "$", "&": "&", "#": "#", "_": "_", "{": "{", "}": "}"}
METADATA_MACROS = {"title", "subtitle", "author", "date", "institute"}
LIST_ENVIRONMENTS = {"itemize", "enumerate", "description"}
BLOCK_ENVIRONMENTS = {"block", "alertblock", "exampleblock"}
WRAPPER_ENVIRONMENTS = {
    "center",
    "columns",
    "column",
    "flushleft",
    "flushright",
    "minipage",
}
MATH_ENVIRONMENTS = {
    "equation",
    "equation*",
    "align",
    "align*",
    "gather",
    "gather*",
    "displaymath",
}
OVERLAY_MACROS = {"only", "uncover", "onslide", "visible", "invisible"}
FORMATTING_MACROS = {
    "textbf",
    "emph",
    "textit",
    "textrm",
    "textsf",
    "texttt",
    "textnormal",
    "underline",
    "alert",
    "structure",
}
DECLARATION_MACROS = {
    "tiny",
    "scriptsize",
    "footnotesize",
    "small",
    "normalsize",
    "large",
    "Large",
    "LARGE",
    "huge",
    "Huge",
    "centering",
    "raggedleft",
    "raggedright",
}
SPACING_MACROS = {"vspace", "hspace", "vspace*", "hspace*"}


@dataclass
class _Fragment:
    text: str
    start: int
    end: int
    formulas: list[NativeRecord] = field(default_factory=list)


def _latex_context():
    # Register macros whose standard arguments must remain attached
    context = get_default_latex_context_db()
    macros = [
        MacroSpec("author", "[{"),
        MacroSpec("date", "[{"),
        MacroSpec("emph", "{"),
        MacroSpec("framesubtitle", "[{"),
        MacroSpec("frametitle", "[{"),
        MacroSpec("hspace", "*{"),
        MacroSpec("hypersetup", "{"),
        MacroSpec("includegraphics", "[{"),
        MacroSpec("institute", "[{"),
        MacroSpec("item", "["),
        MacroSpec("section", "*[{"),
        MacroSpec("subsection", "*[{"),
        MacroSpec("subtitle", "[{"),
        MacroSpec("textbf", "{"),
        MacroSpec("textit", "{"),
        MacroSpec("textnormal", "{"),
        MacroSpec("textrm", "{"),
        MacroSpec("textsf", "{"),
        MacroSpec("texttt", "{"),
        MacroSpec("title", "[{"),
        MacroSpec("underline", "{"),
        MacroSpec("vspace", "*{"),
    ]
    context.add_context_category("a11y-parser", macros=macros, prepend=True)
    return context


class _Parser:
    def __init__(self, text: str, source_file: str):
        # Prepare one tolerant parse with shared source indexing
        self.text = text
        self.source_file = source_file
        self.line_starts = [0]
        for match in re.finditer("\n", text):
            self.line_starts.append(match.end())
        self.metadata: dict[str, str] = {}
        self.metadata_sources: dict[str, NativeSource] = {}
        self.user_macros: list[str] = []
        self.hypersetup: dict[str, str] = {}

    def run(self) -> NativeDocument:
        # Convert the walker tree into source faithful native records
        walker = LatexWalker(
            self.text,
            latex_context=_latex_context(),
            tolerant_parsing=True,
        )
        nodes, _, _ = walker.get_latex_nodes()
        records = self._top_records(nodes)
        return NativeDocument(
            source_file=self.source_file,
            source_text=self.text,
            metadata=self.metadata,
            metadata_sources=self.metadata_sources,
            records=records,
            user_macros=self.user_macros,
            hypersetup=self.hypersetup,
        )

    def _top_records(self, nodes: list[Any]) -> list[NativeRecord]:
        # Recognize preamble declarations and document boundaries
        records: list[NativeRecord] = []
        index = 0
        while index < len(nodes):
            node = nodes[index]
            if isinstance(node, LatexCommentNode) or isinstance(node, LatexCharsNode):
                index += 1
                continue
            if isinstance(node, LatexEnvironmentNode):
                if node.environmentname == "document":
                    records.extend(self._top_records(node.nodelist))
                elif node.environmentname == "frame":
                    records.append(self._frame(node))
                index += 1
                continue
            if not isinstance(node, LatexMacroNode):
                index += 1
                continue
            name = node.macroname
            if name in METADATA_MACROS:
                self._metadata(node, nodes, index)
            elif name == "newcommand" or name == "renewcommand":
                records.append(self._command_definition(node))
            elif name == "def":
                record, index = self._def_definition(node, nodes, index)
                records.append(record)
            elif name == "hypersetup":
                records.append(self._hypersetup(node))
            elif name == "section" or name == "subsection":
                records.append(self._section(node))
            index += 1
        return records

    def _metadata(self, node: LatexMacroNode, siblings: list[Any], index: int) -> None:
        # Store visible metadata text and its exact argument span
        argument, _ = self._required_argument_or_sibling(node, siblings, index)
        if argument is None:
            return
        value = self._text_from_nodes(argument.nodelist)
        self.metadata[node.macroname] = self._normalize(value)
        self.metadata_sources[node.macroname] = self._source(
            argument.pos,
            argument.pos + argument.len,
            f"{node.macroname} argument",
        )

    def _command_definition(self, node: LatexMacroNode) -> NativeRecord:
        # Record a LaTeX command declaration without interpreting its body
        groups = self._argument_groups(node)
        name = ""
        if groups:
            match = re.search(r"\\([A-Za-z@]+)", groups[0].latex_verbatim())
            if match is not None:
                name = match.group(1)
        self._remember_macro(name)
        attrs: dict[str, Any] = {"command": node.macroname, "name": name}
        return NativeRecord(
            kind="definition",
            source=self._source(node.pos, node.pos + node.len, node.macroname),
            attrs=attrs,
        )

    def _def_definition(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
    ) -> tuple[NativeRecord, int]:
        # Collect a primitive definition through its replacement group
        name = ""
        end = node.pos + node.len
        final_index = index
        position = index + 1
        if position < len(siblings) and isinstance(siblings[position], LatexMacroNode):
            name = siblings[position].macroname
        while position < len(siblings):
            sibling = siblings[position]
            end = sibling.pos + sibling.len
            final_index = position
            if isinstance(sibling, LatexGroupNode):
                break
            if isinstance(sibling, LatexEnvironmentNode):
                break
            position += 1
        self._remember_macro(name)
        record = NativeRecord(
            kind="definition",
            source=self._source(node.pos, end, "def"),
            attrs={"command": "def", "name": name},
        )
        return record, final_index

    def _remember_macro(self, name: str) -> None:
        # Keep user command names in declaration order
        if name and name not in self.user_macros:
            self.user_macros.append(name)

    def _section(self, node: LatexMacroNode) -> NativeRecord:
        # Record one outline boundary and its heading text
        argument = self._required_argument(node)
        text = ""
        if argument is not None:
            text = self._normalize(self._text_from_nodes(argument.nodelist))
        level = 1
        if node.macroname == "subsection":
            level = 2
        return NativeRecord(
            kind="section",
            source=self._source(node.pos, node.pos + node.len, node.macroname),
            text=text,
            attrs={"level": level, "command": node.macroname},
        )

    def _hypersetup(self, node: LatexMacroNode) -> NativeRecord:
        # Parse top level hyperlink settings without expanding TeX
        argument = self._required_argument(node)
        settings: dict[str, str] = {}
        if argument is not None:
            raw = self._inside_group(argument)
            for item in self._split_top_level(raw, ","):
                key, separator, value = item.partition("=")
                key = key.strip()
                if not key:
                    continue
                cleaned = ""
                if separator:
                    cleaned = self._strip_outer_braces(value.strip())
                settings[key] = cleaned
                self.hypersetup[key] = cleaned
        return NativeRecord(
            kind="hypersetup",
            source=self._source(node.pos, node.pos + node.len, "hypersetup"),
            attrs={"settings": settings},
        )

    def _frame(self, node: LatexEnvironmentNode) -> NativeRecord:
        # Peel Beamer frame prefixes before parsing body content
        overlay, options, title, content_start = self._frame_prefix(node)
        children = self._content_records(node.nodelist, minimum_pos=content_start)
        if title is not None:
            heading = NativeRecord(
                kind="heading",
                source=self._source(
                    title.pos,
                    title.pos + title.len,
                    "frame title argument",
                ),
                text=self._normalize(self._text_from_nodes(title.nodelist)),
                attrs={"level": 2},
            )
            children.insert(0, heading)
        attrs: dict[str, Any] = {}
        if overlay is not None:
            attrs["overlay"] = overlay
        if options is not None:
            attrs["options"] = options
        pauses = self._count_macro(node.nodelist, "pause")
        if pauses:
            attrs["pauses"] = pauses
        return NativeRecord(
            kind="frame",
            source=self._source(node.pos, node.pos + node.len, "frame"),
            attrs=attrs,
            children=children,
        )

    def _frame_prefix(
        self,
        node: LatexEnvironmentNode,
    ) -> tuple[str | None, str | None, LatexGroupNode | None, int]:
        # Read overlay options and title in their Beamer source order
        cursor = node.pos + len(r"\begin{frame}")
        overlay, cursor = self._delimited_at(cursor, "<", ">")
        options, cursor = self._delimited_at(cursor, "[", "]")
        title = self._group_at(node.nodelist, cursor)
        if title is not None:
            cursor = title.pos + title.len
        return overlay, options, title, cursor

    def _content_records(
        self,
        nodes: list[Any],
        minimum_pos: int = 0,
        maximum_pos: int | None = None,
    ) -> list[NativeRecord]:
        # Split frame content at semantic and paragraph boundaries
        records: list[NativeRecord] = []
        fragments: list[_Fragment] = []
        index = 0
        while index < len(nodes):
            node = nodes[index]
            node_start = node.pos
            node_end = node.pos + node.len
            if node_end <= minimum_pos:
                index += 1
                continue
            if maximum_pos is not None and node_start >= maximum_pos:
                break
            if isinstance(node, LatexCommentNode):
                index += 1
                continue
            if isinstance(node, LatexCharsNode):
                self._chars_fragments(
                    node,
                    fragments,
                    records,
                    minimum_pos,
                    maximum_pos,
                )
                index += 1
                continue
            if isinstance(node, LatexMathNode):
                if node.displaytype == "inline":
                    formula = self._math_node(node, True)
                    self._add_fragment(
                        fragments,
                        node.latex_verbatim(),
                        node.pos,
                        node.pos + node.len,
                        formula,
                    )
                else:
                    self._flush_paragraph(fragments, records)
                    records.append(self._math_node(node, False))
                index += 1
                continue
            if isinstance(node, LatexGroupNode):
                text = self._text_from_nodes(node.nodelist)
                self._add_fragment(fragments, text, node.pos, node.pos + node.len)
                index += 1
                continue
            if isinstance(node, LatexEnvironmentNode):
                self._flush_paragraph(fragments, records)
                records.extend(self._environment_records(node))
                index += 1
                continue
            if not isinstance(node, LatexMacroNode):
                index += 1
                continue
            name = node.macroname
            if name in ESCAPE_MACROS:
                self._add_fragment(
                    fragments,
                    ESCAPE_MACROS[name],
                    node.pos,
                    node.pos + node.len,
                )
            elif name in FORMATTING_MACROS:
                index = self._formatting_macro(node, nodes, index, fragments)
            elif name in DECLARATION_MACROS or name in SPACING_MACROS:
                pass
            elif name == "\\" or name == "newline":
                self._add_fragment(fragments, " ", node.pos, node.pos + node.len)
            elif name == "pause":
                self._flush_paragraph(fragments, records)
            elif name == "frametitle" or name == "framesubtitle":
                self._flush_paragraph(fragments, records)
                heading, index = self._frame_heading(node, nodes, index)
                if heading is not None:
                    records.append(heading)
            elif name == "titlepage" or name == "maketitle":
                self._flush_paragraph(fragments, records)
                records.append(
                    NativeRecord(
                        kind="title_page",
                        source=self._source(node.pos, node.pos + node.len, name),
                        attrs={"command": name},
                    )
                )
            elif name == "includegraphics":
                self._flush_paragraph(fragments, records)
                records.append(self._includegraphics(node))
            elif name in OVERLAY_MACROS:
                self._flush_paragraph(fragments, records)
                overlay, index = self._overlay(node, nodes, index)
                records.append(overlay)
            elif name == "section" or name == "subsection":
                self._flush_paragraph(fragments, records)
                records.append(self._section(node))
            elif name == "hypersetup":
                self._flush_paragraph(fragments, records)
                records.append(self._hypersetup(node))
            elif name == "newcommand" or name == "renewcommand":
                self._flush_paragraph(fragments, records)
                records.append(self._command_definition(node))
            elif name == "def":
                self._flush_paragraph(fragments, records)
                definition, index = self._def_definition(node, nodes, index)
                records.append(definition)
            elif name == "item":
                pass
            else:
                self._flush_paragraph(fragments, records)
                unknown, index = self._unknown_macro(node, nodes, index)
                records.append(unknown)
            index += 1
        self._flush_paragraph(fragments, records)
        return records

    def _chars_fragments(
        self,
        node: LatexCharsNode,
        fragments: list[_Fragment],
        records: list[NativeRecord],
        minimum_pos: int,
        maximum_pos: int | None,
    ) -> None:
        # Divide character data wherever a blank line starts a paragraph
        start = max(node.pos, minimum_pos)
        end = node.pos + node.len
        if maximum_pos is not None:
            end = min(end, maximum_pos)
        if end <= start:
            return
        raw = self.text[start:end]
        cursor = 0
        for match in re.finditer(r"\n[ \t]*\n", raw):
            piece = raw[cursor : match.start()]
            self._add_fragment(fragments, piece, start + cursor, start + match.start())
            self._flush_paragraph(fragments, records)
            cursor = match.end()
        self._add_fragment(fragments, raw[cursor:], start + cursor, end)

    def _add_fragment(
        self,
        fragments: list[_Fragment],
        text: str,
        start: int,
        end: int,
        formula: NativeRecord | None = None,
    ) -> None:
        # Append visible text and optional inline formula provenance
        formulas: list[NativeRecord] = []
        if formula is not None:
            formulas.append(formula)
        fragments.append(_Fragment(text=text, start=start, end=end, formulas=formulas))

    def _flush_paragraph(
        self,
        fragments: list[_Fragment],
        records: list[NativeRecord],
    ) -> None:
        # Emit one normalized paragraph from accumulated inline fragments
        if not fragments:
            return
        text = ""
        formulas: list[NativeRecord] = []
        for fragment in fragments:
            text += fragment.text
            formulas.extend(fragment.formulas)
        normalized = self._normalize(text)
        if normalized:
            start = fragments[0].start
            end = fragments[-1].end
            start, end = self._trim_span(start, end)
            records.append(
                NativeRecord(
                    kind="paragraph",
                    source=self._source(start, end, "paragraph"),
                    text=normalized,
                    children=formulas,
                )
            )
        fragments.clear()

    def _environment_records(self, node: LatexEnvironmentNode) -> list[NativeRecord]:
        # Dispatch one environment while preserving transparent wrappers
        name = node.environmentname
        records: list[NativeRecord] = []
        if name in LIST_ENVIRONMENTS:
            records.append(self._list(node))
        elif name in MATH_ENVIRONMENTS:
            records.append(self._math_environment(node))
        elif name == "tikzpicture":
            records.append(self._tikz(node))
        elif name in BLOCK_ENVIRONMENTS:
            records.append(self._block(node))
        elif name in WRAPPER_ENVIRONMENTS:
            minimum_pos = self._wrapper_content_start(node)
            records.extend(self._content_records(node.nodelist, minimum_pos=minimum_pos))
        else:
            records.append(
                NativeRecord(
                    kind="unknown",
                    source=self._source(node.pos, node.pos + node.len, name),
                    attrs={"environment": name},
                )
            )
        return records

    def _wrapper_content_start(self, node: LatexEnvironmentNode) -> int:
        # Skip required width arguments on transparent sizing wrappers
        start = node.pos + len(r"\begin{" + node.environmentname + "}")
        if node.environmentname != "column" and node.environmentname != "minipage":
            return start
        group = self._group_at(node.nodelist, start)
        if group is None:
            return start
        return group.pos + group.len

    def _list(self, node: LatexEnvironmentNode) -> NativeRecord:
        # Build list items with nested structure and exact end spans
        item_positions: list[int] = []
        for index, child in enumerate(node.nodelist):
            if isinstance(child, LatexMacroNode) and child.macroname == "item":
                item_positions.append(index)
        children: list[NativeRecord] = []
        closing_start = node.pos + node.len - len(r"\end{" + node.environmentname + "}")
        for position, item_index in enumerate(item_positions):
            end_index = len(node.nodelist)
            end_limit = closing_start
            if position + 1 < len(item_positions):
                end_index = item_positions[position + 1]
                end_limit = node.nodelist[end_index].pos
            item_nodes = node.nodelist[item_index + 1 : end_index]
            children.append(
                self._list_item(
                    node.nodelist[item_index],
                    item_nodes,
                    end_limit,
                )
            )
        attrs: dict[str, Any] = {"ordered": node.environmentname == "enumerate"}
        if node.environmentname == "description":
            attrs["description"] = True
        return NativeRecord(
            kind="list",
            source=self._source(node.pos, node.pos + node.len, node.environmentname),
            attrs=attrs,
            children=children,
        )

    def _list_item(
        self,
        item: LatexMacroNode,
        nodes: list[Any],
        end_limit: int,
    ) -> NativeRecord:
        # Separate item text overlays labels formulas and nested blocks
        minimum_pos = item.pos + item.len
        overlay = None
        if nodes and isinstance(nodes[0], LatexCharsNode):
            overlay, minimum_pos = self._overlay_in_chars(nodes[0], minimum_pos)
        parsed = self._content_records(
            nodes,
            minimum_pos=minimum_pos,
            maximum_pos=end_limit,
        )
        text_parts: list[str] = []
        children: list[NativeRecord] = []
        for record in parsed:
            if record.kind == "paragraph":
                if record.text:
                    text_parts.append(record.text)
                children.extend(record.children)
            else:
                children.append(record)
        text = self._normalize(" ".join(text_parts))
        end = self._last_content_end(nodes, minimum_pos, end_limit)
        if end < item.pos + item.len:
            end = item.pos + item.len
        attrs: dict[str, Any] = {}
        label = self._optional_argument(item)
        if label is not None:
            attrs["label"] = self._normalize(self._text_from_nodes(label.nodelist))
        if overlay is not None:
            attrs["overlay"] = overlay
        return NativeRecord(
            kind="list_item",
            source=self._source(item.pos, end, "item"),
            text=text,
            attrs=attrs,
            children=children,
        )

    def _last_content_end(
        self,
        nodes: list[Any],
        minimum_pos: int,
        end_limit: int,
    ) -> int:
        # Find the final noncomment content character before an item boundary
        end = minimum_pos
        for node in nodes:
            if node.pos >= end_limit or isinstance(node, LatexCommentNode):
                continue
            if isinstance(node, LatexCharsNode):
                start = max(node.pos, minimum_pos)
                stop = min(node.pos + node.len, end_limit)
                raw = self.text[start:stop].rstrip()
                if raw:
                    end = max(end, start + len(raw))
            else:
                end = max(end, min(node.pos + node.len, end_limit))
        return end

    def _overlay_in_chars(
        self,
        node: LatexCharsNode,
        minimum_pos: int,
    ) -> tuple[str | None, int]:
        # Remove an item overlay glued to the next character node
        start = max(node.pos, minimum_pos)
        raw = self.text[start : node.pos + node.len]
        match = re.match(r"\s*<([^>]*)>", raw)
        if match is None:
            return None, minimum_pos
        return match.group(1), start + match.end()

    def _block(self, node: LatexEnvironmentNode) -> NativeRecord:
        # Preserve a Beamer block and expose its title as a heading
        cursor = node.pos + len(r"\begin{" + node.environmentname + "}")
        overlay, cursor = self._delimited_at(cursor, "<", ">")
        title = self._group_at(node.nodelist, cursor)
        children: list[NativeRecord] = []
        attrs: dict[str, Any] = {"block_type": node.environmentname}
        if overlay is not None:
            attrs["overlay"] = overlay
        if title is not None:
            title_text = self._normalize(self._text_from_nodes(title.nodelist))
            attrs["title"] = title_text
            children.append(
                NativeRecord(
                    kind="heading",
                    source=self._source(
                        title.pos,
                        title.pos + title.len,
                        "block title argument",
                    ),
                    text=title_text,
                    attrs={"level": 3},
                )
            )
            cursor = title.pos + title.len
        children.extend(self._content_records(node.nodelist, minimum_pos=cursor))
        return NativeRecord(
            kind="block",
            source=self._source(node.pos, node.pos + node.len, node.environmentname),
            attrs=attrs,
            children=children,
        )

    def _frame_heading(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
    ) -> tuple[NativeRecord | None, int]:
        # Consume a frame heading argument whether attached or sibling
        argument, final_index = self._required_argument_or_sibling(node, siblings, index)
        if argument is None:
            return None, index
        attrs: dict[str, Any] = {"level": 2}
        if node.macroname == "framesubtitle":
            attrs["subtitle"] = True
        return (
            NativeRecord(
                kind="heading",
                source=self._source(
                    argument.pos,
                    argument.pos + argument.len,
                    f"{node.macroname} argument",
                ),
                text=self._normalize(self._text_from_nodes(argument.nodelist)),
                attrs=attrs,
            ),
            final_index,
        )

    def _formatting_macro(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
        fragments: list[_Fragment],
    ) -> int:
        # Flow formatting contents into the surrounding text
        argument = self._required_argument(node)
        final_index = index
        overlay = None
        if argument is None:
            overlay, argument, final_index = self._overlay_group_after(siblings, index)
        if argument is None:
            return final_index
        text = self._text_from_nodes(argument.nodelist)
        end = argument.pos + argument.len
        self._add_fragment(fragments, text, node.pos, end)
        if overlay is not None and not text:
            return index
        return final_index

    def _overlay(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
    ) -> tuple[NativeRecord, int]:
        # Capture an overlay command spec and its scoped content
        overlay, argument, final_index = self._overlay_group_after(siblings, index)
        end = node.pos + node.len
        children: list[NativeRecord] = []
        if argument is not None:
            end = argument.pos + argument.len
            children = self._content_records(argument.nodelist)
        elif overlay is None:
            overlay, loose_children, loose_end, loose_index = self._loose_overlay(
                siblings,
                index,
            )
            children.extend(loose_children)
            end = loose_end
            final_index = loose_index
        elif final_index > index:
            sibling = siblings[final_index]
            end = sibling.pos + sibling.len
        attrs: dict[str, Any] = {"command": node.macroname}
        if overlay is not None:
            attrs["overlay"] = overlay
        return (
            NativeRecord(
                kind="overlay",
                source=self._source(node.pos, end, node.macroname),
                attrs=attrs,
                children=children,
            ),
            final_index,
        )

    def _loose_overlay(
        self,
        siblings: list[Any],
        index: int,
    ) -> tuple[str | None, list[NativeRecord], int, int]:
        # Parse an unbraced overlay whose text shares a character node
        children: list[NativeRecord] = []
        if index + 1 >= len(siblings):
            return None, children, siblings[index].pos + siblings[index].len, index
        sibling = siblings[index + 1]
        if not isinstance(sibling, LatexCharsNode):
            return None, children, siblings[index].pos + siblings[index].len, index
        match = re.match(r"\s*<([^>]*)>", sibling.chars)
        if match is None:
            return None, children, siblings[index].pos + siblings[index].len, index
        content_start = sibling.pos + match.end()
        children = self._content_records([sibling], minimum_pos=content_start)
        return match.group(1), children, sibling.pos + sibling.len, index + 1

    def _overlay_group_after(
        self,
        siblings: list[Any],
        index: int,
    ) -> tuple[str | None, LatexGroupNode | None, int]:
        # Find an optional angle spec followed by one argument group
        overlay = None
        position = index + 1
        final_index = index
        if position < len(siblings) and isinstance(siblings[position], LatexCharsNode):
            chars = siblings[position]
            match = re.fullmatch(r"\s*<([^>]*)>\s*", chars.chars)
            if match is not None:
                overlay = match.group(1)
                final_index = position
                position += 1
        while position < len(siblings):
            sibling = siblings[position]
            if isinstance(sibling, LatexCommentNode):
                final_index = position
                position += 1
                continue
            if isinstance(sibling, LatexCharsNode) and not sibling.chars.strip():
                final_index = position
                position += 1
                continue
            if isinstance(sibling, LatexGroupNode):
                return overlay, sibling, position
            break
        return overlay, None, final_index

    def _includegraphics(self, node: LatexMacroNode) -> NativeRecord:
        # Record an image reference and its untouched option text
        argument = self._required_argument(node)
        path = ""
        if argument is not None:
            path = self._inside_group(argument).strip()
        attrs: dict[str, Any] = {"path": path}
        option = self._optional_argument(node)
        if option is not None:
            attrs["options"] = self._inside_group(option).strip()
        return NativeRecord(
            kind="figure",
            source=self._source(node.pos, node.pos + node.len, "includegraphics"),
            attrs=attrs,
        )

    def _tikz(self, node: LatexEnvironmentNode) -> NativeRecord:
        # Keep exact TikZ source and collect labels from node groups
        labels: list[str] = []
        self._tikz_labels(node.nodelist, labels)
        return NativeRecord(
            kind="figure",
            source=self._source(node.pos, node.pos + node.len, "tikzpicture"),
            attrs={"subtype": "diagram", "labels": labels},
        )

    def _tikz_labels(self, nodes: list[Any], labels: list[str]) -> None:
        # Walk TikZ siblings and collect every static node label
        for index, node in enumerate(nodes):
            if isinstance(node, LatexMacroNode) and node.macroname == "node":
                position = index + 1
                while position < len(nodes):
                    sibling = nodes[position]
                    if isinstance(sibling, LatexGroupNode):
                        label = self._normalize(self._tikz_label_text(sibling.nodelist))
                        if label:
                            labels.append(label)
                        break
                    if isinstance(sibling, LatexEnvironmentNode):
                        break
                    position += 1
            if isinstance(node, LatexEnvironmentNode) or isinstance(node, LatexGroupNode):
                self._tikz_labels(node.nodelist, labels)

    def _tikz_label_text(self, nodes: list[Any]) -> str:
        # Preserve unresolved label macros while dropping visual formatting
        text = ""
        for node in nodes:
            if isinstance(node, LatexCommentNode):
                continue
            if isinstance(node, LatexCharsNode):
                text += node.chars
            elif isinstance(node, LatexGroupNode):
                text += self._tikz_label_text(node.nodelist)
            elif isinstance(node, LatexMathNode):
                text += node.latex_verbatim()
            elif isinstance(node, LatexMacroNode):
                name = node.macroname
                if name in ESCAPE_MACROS:
                    text += ESCAPE_MACROS[name]
                elif name in DECLARATION_MACROS or name in SPACING_MACROS:
                    continue
                elif name in FORMATTING_MACROS:
                    argument = self._required_argument(node)
                    if argument is not None:
                        text += self._tikz_label_text(argument.nodelist)
                else:
                    text += node.latex_verbatim()
        return text

    def _math_node(self, node: LatexMathNode, inline: bool) -> NativeRecord:
        # Preserve formula delimiters in source and body TeX in attributes
        raw = node.latex_verbatim()
        tex = self._math_body(raw)
        native_type = "display math"
        if inline:
            native_type = "inline math"
        return NativeRecord(
            kind="formula",
            source=self._source(node.pos, node.pos + node.len, native_type),
            attrs={"tex": tex, "inline": inline, "displaytype": node.displaytype},
        )

    def _math_environment(self, node: LatexEnvironmentNode) -> NativeRecord:
        # Preserve a display math environment and its unexpanded body
        begin = node.pos + len(r"\begin{" + node.environmentname + "}")
        end = node.pos + node.len - len(r"\end{" + node.environmentname + "}")
        tex = self.text[begin:end].strip()
        return NativeRecord(
            kind="formula",
            source=self._source(node.pos, node.pos + node.len, node.environmentname),
            attrs={
                "tex": tex,
                "inline": False,
                "environment": node.environmentname,
            },
        )

    def _math_body(self, raw: str) -> str:
        # Remove one matching pair of math delimiters
        if raw.startswith("$$") and raw.endswith("$$"):
            return raw[2:-2].strip()
        if raw.startswith(r"\[") and raw.endswith(r"\]"):
            return raw[2:-2].strip()
        if raw.startswith(r"\(") and raw.endswith(r"\)"):
            return raw[2:-2].strip()
        if raw.startswith("$") and raw.endswith("$"):
            return raw[1:-1].strip()
        return raw.strip()

    def _unknown_macro(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
    ) -> tuple[NativeRecord, int]:
        # Collect consecutive sibling groups as unknown macro arguments
        args: list[str] = []
        end = node.pos + node.len
        final_index = index
        position = index + 1
        while position < len(siblings):
            sibling = siblings[position]
            if isinstance(sibling, LatexCommentNode):
                break
            if isinstance(sibling, LatexCharsNode) and not sibling.chars.strip():
                position += 1
                continue
            if not isinstance(sibling, LatexGroupNode):
                break
            args.append(self._normalize(self._text_from_nodes(sibling.nodelist)))
            end = sibling.pos + sibling.len
            final_index = position
            position += 1
        attrs: dict[str, Any] = {
            "macro": node.macroname,
            "args": args,
            "user_defined": node.macroname in self.user_macros,
        }
        return (
            NativeRecord(
                kind="unknown",
                source=self._source(node.pos, end, node.macroname),
                attrs=attrs,
            ),
            final_index,
        )

    def _text_from_nodes(self, nodes: list[Any]) -> str:
        # Resolve visible text while retaining inline math verbatim
        text = ""
        for node in nodes:
            if isinstance(node, LatexCommentNode):
                continue
            if isinstance(node, LatexCharsNode):
                text += node.chars
            elif isinstance(node, LatexMathNode):
                text += node.latex_verbatim()
            elif isinstance(node, LatexGroupNode):
                text += self._text_from_nodes(node.nodelist)
            elif isinstance(node, LatexEnvironmentNode):
                if node.environmentname in WRAPPER_ENVIRONMENTS:
                    text += self._text_from_nodes(node.nodelist)
            elif isinstance(node, LatexMacroNode):
                name = node.macroname
                if name in ESCAPE_MACROS:
                    text += ESCAPE_MACROS[name]
                elif name == "\\" or name == "newline":
                    text += " "
                elif name in FORMATTING_MACROS:
                    argument = self._required_argument(node)
                    if argument is not None:
                        text += self._text_from_nodes(argument.nodelist)
                elif name in DECLARATION_MACROS or name in SPACING_MACROS:
                    continue
                else:
                    groups = self._argument_groups(node)
                    for group in groups:
                        text += self._text_from_nodes(group.nodelist)
        return text

    def _count_macro(self, nodes: list[Any], name: str) -> int:
        # Count one macro recursively within groups and environments
        count = 0
        for node in nodes:
            if isinstance(node, LatexMacroNode) and node.macroname == name:
                count += 1
            if isinstance(node, LatexEnvironmentNode) or isinstance(node, LatexGroupNode):
                count += self._count_macro(node.nodelist, name)
        return count

    def _required_argument(self, node: LatexMacroNode) -> LatexGroupNode | None:
        # Return the final brace argument attached to a macro
        groups = self._argument_groups(node)
        if not groups:
            return None
        for group in reversed(groups):
            if group.delimiters == ("{", "}"):
                return group
        return None

    def _optional_argument(self, node: LatexMacroNode) -> LatexGroupNode | None:
        # Return the first bracket argument attached to a macro
        groups = self._argument_groups(node)
        for group in groups:
            if group.delimiters == ("[", "]"):
                return group
        return None

    def _argument_groups(self, node: LatexMacroNode) -> list[LatexGroupNode]:
        # Collect parsed group arguments without a comprehension
        groups: list[LatexGroupNode] = []
        if node.nodeargd is None:
            return groups
        for argument in node.nodeargd.argnlist:
            if isinstance(argument, LatexGroupNode):
                groups.append(argument)
        return groups

    def _required_argument_or_sibling(
        self,
        node: LatexMacroNode,
        siblings: list[Any],
        index: int,
    ) -> tuple[LatexGroupNode | None, int]:
        # Fall back to the following group for incomplete macro databases
        argument = self._required_argument(node)
        if argument is not None:
            return argument, index
        position = index + 1
        while position < len(siblings):
            sibling = siblings[position]
            if isinstance(sibling, LatexCommentNode):
                position += 1
                continue
            if isinstance(sibling, LatexCharsNode) and not sibling.chars.strip():
                position += 1
                continue
            if isinstance(sibling, LatexGroupNode):
                return sibling, position
            break
        return None, index

    def _group_at(self, nodes: list[Any], position: int) -> LatexGroupNode | None:
        # Find a group beginning at one exact source position
        for node in nodes:
            if node.pos < position and node.pos + node.len <= position:
                continue
            if node.pos == position and isinstance(node, LatexGroupNode):
                return node
            if node.pos > position:
                break
        return None

    def _delimited_at(
        self,
        position: int,
        opening: str,
        closing: str,
    ) -> tuple[str | None, int]:
        # Peel one simple Beamer prefix at the current position
        if position >= len(self.text) or self.text[position] != opening:
            return None, position
        end = self.text.find(closing, position + 1)
        if end == -1:
            return None, position
        return self.text[position + 1 : end], end + 1

    def _inside_group(self, node: LatexGroupNode) -> str:
        # Return group source without its outer delimiters
        raw = node.latex_verbatim()
        if len(raw) >= 2:
            return raw[1:-1]
        return raw

    def _split_top_level(self, value: str, delimiter: str) -> list[str]:
        # Split text only where brace nesting is balanced
        parts: list[str] = []
        start = 0
        depth = 0
        for index, character in enumerate(value):
            if character == "{":
                depth += 1
            elif character == "}" and depth:
                depth -= 1
            elif character == delimiter and depth == 0:
                parts.append(value[start:index])
                start = index + 1
        parts.append(value[start:])
        return parts

    def _strip_outer_braces(self, value: str) -> str:
        # Remove one balanced pair of surrounding braces
        if not value.startswith("{") or not value.endswith("}"):
            return value
        depth = 0
        for index, character in enumerate(value):
            if character == "{":
                depth += 1
            elif character == "}":
                depth -= 1
                if depth == 0 and index != len(value) - 1:
                    return value
        if depth == 0:
            return value[1:-1]
        return value

    def _normalize(self, value: str) -> str:
        # Collapse source whitespace into readable native text
        return re.sub(r"\s+", " ", value).strip()

    def _trim_span(self, start: int, end: int) -> tuple[int, int]:
        # Remove surrounding source whitespace from a text span
        while start < end and self.text[start].isspace():
            start += 1
        while end > start and self.text[end - 1].isspace():
            end -= 1
        return start, end

    def _source(self, start: int, end: int, native_type: str) -> NativeSource:
        # Convert character offsets to inclusive one based source lines
        safe_start = max(0, min(start, len(self.text)))
        safe_end = max(safe_start, min(end, len(self.text)))
        line_start = bisect_right(self.line_starts, safe_start)
        line_position = safe_start
        if safe_end > safe_start:
            line_position = safe_end - 1
        line_end = bisect_right(self.line_starts, line_position)
        return NativeSource(
            file=self.source_file,
            line_start=line_start,
            line_end=line_end,
            char_start=safe_start,
            char_end=safe_end,
            native_type=native_type,
            raw=self.text[safe_start:safe_end],
        )


def parse(
    source: str | Path | Bundle,
    source_file: str = "main.tex",
) -> NativeDocument:
    # Parse source text a file or a normalized project bundle
    if isinstance(source, Bundle):
        path = source.root / source.main_file
        text = path.read_text(encoding="utf-8")
        return _Parser(text, source.main_file).run()
    if isinstance(source, Path):
        return parse_file(source, source_file=source_file)
    return _Parser(source, source_file).run()


def parse_file(path: Path, source_file: str | None = None) -> NativeDocument:
    # Read one TeX file or discover the main file in a project
    if path.is_dir():
        return parse(Bundle.from_path(path))
    text = path.read_text(encoding="utf-8")
    relative_name = source_file
    if relative_name is None:
        relative_name = path.name
    return _Parser(text, relative_name).run()
