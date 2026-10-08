#!/usr/bin/env python3
"""Explicit, character-preserving native Word superscript/subscript edits.

Only ZIP XML payloads that actually change are serialized. No chemistry parser,
Unicode lookalike substitution, font-size inference, or whole-document rebuild.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from io import BytesIO
import json
import math
from pathlib import Path
import re
import sys
import unicodedata
import zipfile

from lxml import etree


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
M = "http://schemas.openxmlformats.org/officeDocument/2006/math"
NS = {"w": W, "m": M}
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PART_RE = re.compile(r"word/(?:document|header[0-9]*|footer[0-9]*|footnotes|endnotes)\.xml\Z")
RPR_ORDER = ("rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline "
             "shadow emboss imprint noProof snapToGrid vanish webHidden color "
             "spacing w kern position sz szCs highlight u effect bdr shd fitText "
             "vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange").split()
RPR_RANK = {"{" + W + "}" + name: i for i, name in enumerate(RPR_ORDER)}
REVISION_NAMES = {"ins", "del", "moveFrom", "moveTo", "cellIns", "cellDel", "cellMerge"}
FIELD_NAMES = {"fldSimple", "fldChar", "instrText", "delInstrText"}


class Refusal(ValueError):
    pass


def w(name):
    return "{" + W + "}" + name


def local(node):
    return etree.QName(node).localname if isinstance(node.tag, str) else ""


def is_revision(node):
    return (isinstance(node.tag, str) and etree.QName(node).namespace == W
            and (local(node) in REVISION_NAMES or local(node).endswith("Change")
                 or local(node).startswith(("moveFromRange", "moveToRange"))))


def normal_char(char):
    """Only Unicode characters explicitly named SUPERSCRIPT/SUBSCRIPT.

    In particular U+2212 MINUS SIGN, ordinary digits and mathematical alphabets
    are left untouched. Unknown modifier-letter glyphs are not guessed.
    """
    name = unicodedata.name(char, "")
    if "SUPERSCRIPT" in name or "SUBSCRIPT" in name:
        candidate = unicodedata.normalize("NFKC", char)
        if len(candidate) == 1:
            return candidate
    return char


def normal(text):
    return "".join(normal_char(c) for c in text)


def notation(text):
    """Parse baseline text and flat _{...}/^{...}; no LaTeX interpretation."""
    result = []
    i = 0
    while i < len(text):
        char = text[i]
        if char in "_^":
            if i + 1 >= len(text) or text[i + 1] != "{":
                raise Refusal("notation 中 _ 或 ^ 必须写成 _{...} / ^{...}。")
            end = text.find("}", i + 2)
            if end < 0 or end == i + 2:
                raise Refusal("notation 角标分组缺少右括号或为空。")
            body = text[i + 2:end]
            if any(c in "{}_^" for c in body):
                raise Refusal("notation 不支持嵌套角标、嵌套括号或 LaTeX。")
            style = "subscript" if char == "_" else "superscript"
            result.extend((normal_char(c), style) for c in body)
            i = end + 1
        elif char in "{}":
            raise Refusal("notation 的花括号只能用于 _{...} / ^{...}。")
        else:
            result.append((normal_char(char), "baseline"))
            i += 1
    return result


@dataclass
class Paragraph:
    part: str
    index: int
    element: object
    chars: list
    text: str
    normalized: str
    protected: list


def nearest_paragraph(node):
    for ancestor in node.iterancestors():
        if ancestor.tag == w("p"):
            return ancestor
    return None


def text_only_run(run):
    if run.tag != w("r"):
        return False
    if sum(child.tag == w("rPr") for child in run) > 1:
        return False
    if any(child.tag not in (w("rPr"), w("t")) for child in run):
        return False
    return all(not list(t) and not (set(t.attrib) - {XML_SPACE})
               for t in run if t.tag == w("t"))


def allowed_runs(paragraph):
    """Assign a segment to continuous text-only runs in exactly one container.

    Hyperlinks are separate containers, and all non-run elements (including
    bookmarks/proofing markers) are barriers. Unsupported wrappers are refused.
    """
    result = {}
    serial = 0

    def scan(container):
        nonlocal serial
        serial += 1
        for child in container:
            if text_only_run(child):
                result[child] = serial
            else:
                serial += 1

    for child in paragraph:
        if child.tag == w("hyperlink"):
            scan(child)
            serial += 1
        elif text_only_run(child):
            result[child] = serial
        else:
            serial += 1
    return result


def protected_reasons(paragraph, field_paragraphs):
    reasons = set()
    if paragraph in field_paragraphs:
        reasons.add("field")
    for node in list(paragraph.iter()) + list(paragraph.iterancestors()):
        if node.tag == w("sdt"):
            reasons.add("sdt")
        if is_revision(node):
            reasons.add("revision")
        if isinstance(node.tag, str) and etree.QName(node).namespace == W and local(node) in FIELD_NAMES:
            reasons.add("field")
    return sorted(reasons)


def paragraphs(part, root):
    # Complex fields can span paragraph boundaries; mark their result paragraphs.
    field_paragraphs = set()
    depth = 0
    for node in root.iter():
        if node.tag == w("p") and depth:
            field_paragraphs.add(node)
        if node.tag == w("fldChar"):
            para = nearest_paragraph(node)
            if para is not None:
                field_paragraphs.add(para)
            kind = node.get(w("fldCharType"))
            if kind == "begin":
                depth += 1
            elif kind == "end":
                depth = max(0, depth - 1)
    result = []
    for index, para in enumerate(root.iter(w("p")), 1):
        segments = allowed_runs(para)
        offsets = {}
        chars = []
        for node in para.iter():
            if node.tag not in (w("t"), w("delText")) or nearest_paragraph(node) is not para:
                continue
            run = node.getparent()
            offset = offsets.get(run, 0)
            for char in node.text or "":
                chars.append((char, run, offset, segments.get(run)))
                offset += 1
            offsets[run] = offset
        text = "".join(item[0] for item in chars)
        result.append(Paragraph(part, index, para, chars, text, normal(text),
                                protected_reasons(para, field_paragraphs)))
    return result


def package(path):
    raw = path.read_bytes()
    archive = zipfile.ZipFile(BytesIO(raw))
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise Refusal("DOCX ZIP 含重名部件，拒绝产生歧义。")
    if "word/document.xml" not in names:
        raise Refusal("输入不包含 word/document.xml，不能作为此脚本支持的 DOCX。")
    payloads = {info.filename: archive.read(info) for info in archive.infolist()}
    trees = {}
    para = []
    for name, payload in payloads.items():
        if PART_RE.fullmatch(name):
            parser = etree.XMLParser(resolve_entities=False, no_network=True, remove_blank_text=False)
            tree = etree.parse(BytesIO(payload), parser)
            if tree.docinfo.doctype:
                raise Refusal("DOCX XML 不允许 DTD: " + name)
            if etree.QName(tree.getroot()).namespace != W:
                raise Refusal("仅支持 Transitional WordprocessingML 命名空间: " + name)
            trees[name] = tree
            para.extend(paragraphs(name, tree.getroot()))
    return raw, archive, payloads, trees, para


def describe(para):
    return {"part": para.part, "paragraph": para.index, "text": para.text}


def audit(path):
    raw, archive, payloads, trees, paras = package(path)
    report = {"operation": "audit", "input": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
              "scope": list(trees), "unicode_scripts": [], "native_scripts": [],
              "manual_positions": [], "small_font_candidates": [], "omml": [],
              "protected_objects": [], "notes": [
                  "小字号仅为候选，不自动判错；只报告显式字号，未计算样式继承。",
                  "仅支持列出的 WordprocessingML 部件；不读取样式继承、嵌入对象或严格型 OOXML。",
                  "Unicode 规范化限于名称含 SUPERSCRIPT / SUBSCRIPT 且 NFKC 为单字符者；⁻/₋ 的对应普通字符为数学负号 −，不是 ASCII '-'。"]}
    for para in paras:
        where = describe(para)
        glyphs = [{"offset": i, "character": char, "normal": normal_char(char),
                   "codepoint": f"U+{ord(char):04X}"}
                  for i, char in enumerate(para.text) if normal_char(char) != char]
        if glyphs:
            report["unicode_scripts"].append({**where, "characters": glyphs})
        if para.protected:
            report["protected_objects"].append({**where, "kinds": para.protected})
        runs = [r for r in para.element.iter(w("r")) if nearest_paragraph(r) is para.element]
        sizes = []
        for run in runs:
            sz = run.find("w:rPr/w:sz", NS)
            try:
                sizes.append(float(sz.get(w("val"))) / 2 if sz is not None else None)
            except (TypeError, ValueError):
                sizes.append(None)
        max_size = max((n for n in sizes if n is not None), default=0)
        for index, (run, size) in enumerate(zip(runs, sizes), 1):
            rtext = "".join(t.text or "" for t in run.iter(w("t")))
            detail = {**where, "run": index, "run_text": rtext}
            for node in run.findall("w:rPr/w:vertAlign", NS):
                if node.get(w("val")) in ("superscript", "subscript"):
                    report["native_scripts"].append({**detail, "value": node.get(w("val"))})
            for node in run.findall("w:rPr/w:position", NS):
                report["manual_positions"].append({**detail, "half_points": node.get(w("val"))})
            if rtext and size is not None and (size < max_size or size <= 9):
                report["small_font_candidates"].append({**detail, "size_pt": size,
                                                        "paragraph_max_explicit_size_pt": max_size,
                                                        "status": "candidate_only"})
    for name, tree in trees.items():
        root = tree.getroot()
        math_count = len(list(root.iter("{" + M + "}oMath")))
        math_para_count = len(list(root.iter("{" + M + "}oMathPara")))
        if math_count or math_para_count:
            report["omml"].append({"part": name, "oMath": math_count, "oMathPara": math_para_count})
        counts = {}
        for name_ in ("bookmarkStart", "bookmarkEnd", "hyperlink", "drawing", "object"):
            count = len(list(root.iter(w(name_))))
            if count:
                counts[name_] = count
        if counts:
            report["protected_objects"].append({"part": name, "boundary_object_counts": counts})
    report["counts"] = {key: len(report[key]) for key in ("unicode_scripts", "native_scripts",
                           "manual_positions", "small_font_candidates", "protected_objects")}
    report["counts"]["omml_equations"] = sum(row["oMath"] for row in report["omml"])
    report["status"] = "audited"
    archive.close()
    return report


def mapping_rows(path):
    content = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(content, dict) or set(content) != {"replacements"}:
        raise Refusal("映射根对象必须只包含 replacements 数组。")
    rows = content["replacements"]
    if not isinstance(rows, list) or not rows:
        raise Refusal("replacements 必须是非空数组。")
    allowed = {"find", "notation", "expected_count", "part", "paragraph_contains", "base_size_pt"}
    result = []
    for number, row in enumerate(rows, 1):
        if not isinstance(row, dict) or set(row) - allowed:
            raise Refusal(f"映射 {number}: 包含未知字段或不是对象。")
        if any(not isinstance(row.get(key), str) or not row[key] for key in ("find", "notation")):
            raise Refusal(f"映射 {number}: find / notation 必须是非空字符串。")
        if type(row.get("expected_count")) is not int or row["expected_count"] < 1:
            raise Refusal(f"映射 {number}: expected_count 必须是正整数。")
        for key in ("part", "paragraph_contains"):
            if key in row and (not isinstance(row[key], str) or not row[key]):
                raise Refusal(f"映射 {number}: {key} 必须是非空字符串。")
        tokens = notation(row["notation"])
        plain = "".join(char for char, _ in tokens)
        if normal(row["find"]) != plain:
            raise Refusal(f"映射 {number}: 拒绝语义字符变化；find 规范化后为 {normal(row['find'])!r}，"
                          f"notation 去标记后为 {plain!r}。仅允许 Unicode 上下标到普通字符。")
        half_points = None
        if "base_size_pt" in row:
            size = row["base_size_pt"]
            if (isinstance(size, bool) or not isinstance(size, (int, float)) or not math.isfinite(size)
                    or size <= 0 or size > 400 or (size * 2) != int(size * 2)):
                raise Refusal(f"映射 {number}: base_size_pt 必须是 0–400 范围内的正半磅倍数。")
            half_points = str(int(size * 2))
        result.append((row, tokens, half_points))
    return result


def property_value(rpr, name, value):
    tag = w(name)
    nodes = rpr.findall(tag)
    if len(nodes) == 1 and nodes[0].get(w("val")) == value:
        return
    for node in nodes:
        rpr.remove(node)
    node = etree.Element(tag)
    node.set(w("val"), value)
    rank = RPR_RANK[tag]
    for i, old in enumerate(rpr):
        if RPR_RANK.get(old.tag, -1) > rank:
            rpr.insert(i, node)
            return
    rpr.append(node)


def styled_rpr(run, style, size):
    source = run.find(w("rPr"))
    rpr = deepcopy(source) if source is not None else etree.Element(w("rPr"))
    property_value(rpr, "vertAlign", style)
    for node in rpr.findall(w("position")):
        rpr.remove(node)
    if size is not None:
        property_value(rpr, "sz", size)
        property_value(rpr, "szCs", size)
    return rpr


def same_rpr(left, right):
    if left is None or right is None:
        return left is right
    # Comparing structural values avoids namespace-prefix/tail formatting noise.
    def structure(node):
        return (node.tag, tuple(sorted(node.attrib.items())), node.text if node.text and node.text.strip() else None,
                tuple(structure(child) for child in node))
    return structure(left) == structure(right)


def rewrite_run(run, edits):
    original = "".join(node.text or "" for node in run if node.tag == w("t"))
    original_rpr = run.find(w("rPr"))
    pieces = []
    changed = False
    cache = {}
    for offset, char in enumerate(original):
        action = edits.get(offset)
        if action is None:
            out_char, rpr = char, original_rpr
        else:
            out_char, style, size = action
            key = (style, size)
            if key not in cache:
                cache[key] = styled_rpr(run, style, size)
            rpr = cache[key]
        changed = changed or out_char != char or not same_rpr(rpr, original_rpr)
        if pieces and same_rpr(pieces[-1][1], rpr):
            pieces[-1][0] += out_char
        else:
            pieces.append([out_char, rpr])
    if not changed:
        return False
    parent = run.getparent()
    position = parent.index(run)
    for i, (text, rpr) in enumerate(pieces):
        replacement = deepcopy(run)
        for child in list(replacement):
            replacement.remove(child)
        if rpr is not None:
            replacement.append(deepcopy(rpr))
        node = etree.SubElement(replacement, w("t"))
        if text[:1].isspace() or text[-1:].isspace():
            node.set(XML_SPACE, "preserve")
        node.text = text
        replacement.tail = run.tail if i == len(pieces) - 1 else None
        parent.insert(position + i, replacement)
    parent.remove(run)
    return True


def apply(input_path, mapping_path, output_path):
    if output_path.exists():
        raise Refusal("输出已存在，拒绝覆盖: " + str(output_path))
    if input_path.resolve() == output_path.resolve():
        raise Refusal("输出不得覆盖输入。")
    rows = mapping_rows(mapping_path)
    raw, archive, payloads, trees, paras = package(input_path)
    report = {"operation": "apply", "input": str(input_path), "output": str(output_path),
              "input_sha256": hashlib.sha256(raw).hexdigest(), "mappings": [], "errors": []}
    all_edits = {}
    run_parts = {}
    occupied = set()
    for number, (row, tokens, size) in enumerate(rows, 1):
        search = normal(row["find"])
        hits = []
        if "part" in row and row["part"] not in trees:
            report["errors"].append(f"映射 {number}: part 不存在或不在受支持范围: {row['part']}")
        for para in paras:
            if "part" in row and row["part"] != para.part:
                continue
            if "paragraph_contains" in row and normal(row["paragraph_contains"]) not in para.normalized:
                continue
            start = 0
            while True:
                start = para.normalized.find(search, start)
                if start < 0:
                    break
                selected = para.chars[start:start + len(search)]
                detail = {**describe(para), "start": start, "length": len(search)}
                hits.append(detail)
                label = f"映射 {number}, {para.part}, 段落 {para.index}, 字符 {start}"
                if para.protected:
                    report["errors"].append(label + ": 段落含受保护对象 " + ", ".join(para.protected))
                elif len({item[3] for item in selected}) != 1 or selected[0][3] is None:
                    report["errors"].append(label + ": 目标跨越书签/超链接/非纯文本 run/其他 XML 边界；拒绝处理。")
                else:
                    for item, token in zip(selected, tokens):
                        _, run, offset, _ = item
                        key = (run, offset)
                        if key in occupied:
                            report["errors"].append(label + ": 映射或命中范围重叠。")
                            break
                        occupied.add(key)
                        all_edits.setdefault(run, {})[offset] = (token[0], token[1], size)
                        run_parts[run] = para.part
                start += 1
        report["mappings"].append({"mapping": number, "expected_count": row["expected_count"],
                                   "actual_count": len(hits), "matches": hits})
        if len(hits) != row["expected_count"]:
            report["errors"].append(f"映射 {number}: 期望 {row['expected_count']} 处，实际 {len(hits)} 处；未写输出。")
    if report["errors"]:
        archive.close()
        report["status"] = "refused"
        return report
    changed_parts = set()
    changed_runs = 0
    for run, edits in all_edits.items():
        if rewrite_run(run, edits):
            changed_runs += 1
            changed_parts.add(run_parts[run])
    updated = dict(payloads)
    for name in changed_parts:
        updated[name] = etree.tostring(trees[name], encoding="UTF-8", xml_declaration=True, standalone=True)
    if changed_parts:
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as output:
            output.comment = archive.comment
            for info in archive.infolist():
                output.writestr(info, updated[info.filename])
        out_bytes = buffer.getvalue()
    else:
        out_bytes = raw
    archive.close()
    # Exclusive creation also guards against a file appearing after preflight.
    created = False
    try:
        with output_path.open("xb") as handle:
            created = True
            handle.write(out_bytes)
    except Exception:
        if created:
            output_path.unlink(missing_ok=True)
        raise
    report.update(status="changed" if changed_parts else "unchanged", changed_parts=sorted(changed_parts),
                  changed_runs=changed_runs, output_sha256=hashlib.sha256(out_bytes).hexdigest(),
                  unchanged_part_payloads_verified=all(updated[name] == payloads[name]
                      for name in payloads if name not in changed_parts),
                  input_unchanged_verified=input_path.read_bytes() == raw,
                  idempotent_copy=not bool(changed_parts))
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    inspect = commands.add_parser("audit", help="只读审计；小字号只列候选")
    inspect.add_argument("input", type=Path)
    inspect.add_argument("--report", type=Path, required=True)
    edit = commands.add_parser("apply", help="显式映射到 Word 原生上下标；全量预检后写新文件")
    edit.add_argument("input", type=Path)
    edit.add_argument("mapping", type=Path)
    edit.add_argument("output", type=Path)
    edit.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    sources = [args.input]
    if args.operation == "apply":
        sources.extend([args.mapping, args.output])
    if any(args.report.resolve() == path.resolve() for path in sources):
        parser.error("report 路径不得与输入、映射或输出相同。")
    if args.report.exists():
        parser.error("report 已存在；请选择新路径以保留原报告。")
    try:
        result = audit(args.input) if args.operation == "audit" else apply(args.input, args.mapping, args.output)
    except (OSError, ValueError, zipfile.BadZipFile, etree.XMLSyntaxError) as exc:
        result = {"operation": args.operation, "status": "refused", "errors": [str(exc)]}
    with args.report.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "errors", "changed_parts") if key in result},
                     ensure_ascii=False))
    return 2 if result["status"] == "refused" else 0


if __name__ == "__main__":
    sys.exit(main())
