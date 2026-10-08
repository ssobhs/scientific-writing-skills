"""Explicit native Word character formatting; no scientific-role inference.

Omitted keys preserve direct formatting; None removes the selected override.
Only plain text runs are accepted for local edits. Existing package surgery is
outside this API; use native_scripts.py for its audited range-edit workflow.
"""
from copy import deepcopy
import math
import re

from docx.enum.text import WD_COLOR_INDEX, WD_UNDERLINE
from docx.oxml.ns import qn
from docx.shared import Pt, RGBColor
from docx.text.run import Run

BOOLS = {"bold", "italic", "strike", "double_strike", "small_caps", "all_caps"}
SLOTS = {"font_ascii": "ascii", "font_hansi": "hAnsi", "font_eastasia": "eastAsia", "font_cs": "cs"}
UNDERLINES = {"single": WD_UNDERLINE.SINGLE, "double": WD_UNDERLINE.DOUBLE,
              "dotted": WD_UNDERLINE.DOTTED, "dash": WD_UNDERLINE.DASH,
              "wave": WD_UNDERLINE.WAVY, "words": WD_UNDERLINE.WORDS}
HIGHLIGHTS = {name.lower(): getattr(WD_COLOR_INDEX, name) for name in
              ("YELLOW", "BRIGHT_GREEN", "TURQUOISE", "PINK", "BLUE", "RED",
               "DARK_BLUE", "TEAL", "GREEN", "VIOLET", "DARK_RED", "DARK_YELLOW",
               "GRAY_50", "GRAY_25", "BLACK", "WHITE")}
KEYS = BOOLS | set(SLOTS) | {"underline", "vertical", "size_pt", "color", "highlight"}


def _validate(fmt):
    if not isinstance(fmt, dict) or set(fmt) - KEYS:
        raise ValueError("format must be a dict with supported keys only")
    for key, value in fmt.items():
        if value is None:
            continue
        if key in BOOLS and type(value) is not bool:
            raise ValueError(f"{key}: expected bool or None")
        if key in SLOTS and (not isinstance(value, str) or not value.strip()):
            raise ValueError(f"{key}: expected non-empty font name or None")
        if key == "vertical" and value not in ("baseline", "subscript", "superscript"):
            raise ValueError("vertical: baseline, subscript, superscript or None")
        if key == "size_pt" and (type(value) not in (int, float) or not math.isfinite(value)
                                 or not 1 <= value <= 1638 or value * 2 != int(value * 2)):
            raise ValueError("size_pt: finite half-point value in 1..1638")
        if key == "color" and (not isinstance(value, str) or not re.fullmatch(r"[0-9A-Fa-f]{6}", value)):
            raise ValueError("color: six hex digits without #")
        if key == "underline" and type(value) is not bool and (not isinstance(value, str) or value not in UNDERLINES):
            raise ValueError("unsupported underline")
        if key == "highlight" and (not isinstance(value, str) or value not in HIGHLIGHTS):
            raise ValueError("unsupported highlight")


def _safe_paragraph(p):
    # Walk the whole XML part: complex fields may span paragraph boundaries.
    root = p.getroottree().getroot()
    depth = 0
    protected = set()
    for node in root.iter():
        if node.tag == qn('w:p') and depth:
            protected.add(node)
        if node.tag == qn('w:fldChar'):
            para = next((a for a in node.iterancestors() if a.tag == qn('w:p')), None)
            if para is not None:
                protected.add(para)
            kind = node.get(qn('w:fldCharType'))
            if kind == 'begin':
                depth += 1
            elif kind == 'end':
                depth = max(0, depth - 1)
    if p in protected:
        raise ValueError('paragraph participates in a complex field')
    for node in list(p.iter()) + list(p.iterancestors()):
        if not isinstance(node.tag, str) or not node.tag.startswith(qn('w:')):
            continue
        name = node.tag.split('}', 1)[1]
        if (name in {'sdt', 'fldSimple', 'fldChar', 'instrText', 'delInstrText',
                     'ins', 'del', 'moveFrom', 'moveTo', 'cellIns', 'cellDel', 'cellMerge'}
                or name.endswith('Change') or name.startswith(('moveFromRange', 'moveToRange'))):
            raise ValueError('paragraph contains a field, revision, or content control')


def _plain(run):
    # Refuse fields, links, revisions, equations, pictures and opaque objects.
    if run._r.getparent() is None or run._r.getparent().tag != qn("w:p"):
        raise ValueError("local formatting requires a direct paragraph text run")
    allowed = {qn("w:rPr"), qn("w:t")}
    if any(child.tag not in allowed for child in run._r):
        raise ValueError("run contains non-text content; preserve it through an object-aware workflow")
    _safe_paragraph(run._r.getparent())


def _apply(run, fmt):
    for key, value in fmt.items():
        if key in BOOLS:
            setattr(run.font, key, value)
        elif key in SLOTS:
            fonts = run._r.get_or_add_rPr().get_or_add_rFonts()
            slot = SLOTS[key]
            theme = "cstheme" if slot == "cs" else slot + "Theme"
            for attr in (slot, theme):
                fonts.attrib.pop(qn("w:" + attr), None)
            if value is not None:
                fonts.set(qn("w:" + slot), value)
        elif key == "vertical":
            rpr = run._r.get_or_add_rPr()
            rpr._remove_vertAlign()
            if value is not None:
                # Explicit native alignment replaces manual baseline shifting.
                for position in list(rpr.findall(qn('w:position'))):
                    rpr.remove(position)
                rpr.get_or_add_vertAlign().val = value
        elif key == "size_pt":
            run.font.size = None if value is None else Pt(value)
        elif key == "color":
            run.font.color.rgb = None if value is None else RGBColor.from_string(value)
        elif key == "underline":
            run.font.underline = UNDERLINES[value] if isinstance(value, str) else value
        elif key == "highlight":
            run.font.highlight_color = None if value is None else HIGHLIGHTS[value]
    if run.font.strike is True and run.font.double_strike is True:
        raise ValueError("strike and double_strike cannot both be directly enabled")


def apply_run_format(run, **fmt):
    """Format an entire explicitly selected plain-text run atomically.

    Do not use on arbitrary search matches without resolving semantic scope.
    Text and all unspecified direct formatting remain unchanged. Style-derived
    effective values are not computed. None clears one direct override only.
    """
    _validate(fmt)
    _plain(run)
    if not fmt:
        return run
    clone = deepcopy(run._r)
    _apply(Run(clone, run._parent), fmt)
    # Preserve the original element identity and text children.
    old = run._r.rPr
    new = clone.rPr
    if old is not None:
        run._r.remove(old)
    if new is not None:
        run._r.insert(0, new)
    return run


def append_spans(paragraph, spans):
    """Append [{text: str, format: {...}}, ...] as native Word runs.

    Input is fully preflighted before insertion. Nothing is inferred from text;
    numeric indices vs upright descriptive subscripts must be supplied explicitly.
    """
    _safe_paragraph(paragraph._p)
    prepared = []
    from docx.oxml import OxmlElement
    for span in spans:
        if not isinstance(span, dict) or set(span) - {"text", "format"} or not isinstance(span.get("text"), str):
            raise ValueError("each span requires text and optional format")
        text = span["text"]
        if any(ord(c) < 32 and c not in "\t\n\r" for c in text):
            raise ValueError("text contains an XML control character")
        fmt = span.get("format", {})
        _validate(fmt)
        elem = OxmlElement("w:r")
        run = Run(elem, paragraph)
        run.text = text
        _apply(run, fmt)
        prepared.append(run)
    for run in prepared:
        paragraph._p.append(run._r)
    return prepared
