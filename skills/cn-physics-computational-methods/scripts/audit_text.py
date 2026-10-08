#!/usr/bin/env python3
"""Offline lexical review aid. Never edits inputs or certifies scientific fidelity.

Exit 0 means a report was produced, including when review is required. Exit 2
means invalid input. Only the standard library is used; no model/network calls.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

VERSION = "1.0"
GREEK = dict(zip(
    "α β γ δ ε ζ η θ ι κ λ μ ν ξ π ρ σ τ υ φ χ ψ ω Γ Δ Θ Λ Ξ Π Σ Φ Ψ Ω".split(),
    "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi pi rho sigma tau upsilon phi chi psi omega Gamma Delta Theta Lambda Xi Pi Sigma Phi Psi Omega".split()))
GREEK.update({"ϵ": "varepsilon", "ϑ": "vartheta", "ϕ": "varphi", "ς": "varsigma"})
NUMBER = r"[+\-−]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-−]?\d+)?(?:\s*[×*]\s*10\s*\^?\s*[+\-−]?\d+)?"
UNIT = r"(?:kcal|kJ|meV|eV|Ry|Ha|THz|Hz|MPa|GPa|Pa|mV|V|mA|A|amu|mol|fs|ps|ns|ms|s|pm|nm|cm|[µμ]m|m|Å|Å|°C|K|%)"
POWER = r"(?:\s*\^\s*[+\-−]?\d+|[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻]+)?"
QUANTITY_RE = re.compile(r"(?<![A-Za-z0-9_.])" + NUMBER + r"\s*" + UNIT + POWER + r"(?:\s*[/·]\s*" + UNIT + POWER + r")*(?![A-Za-z])")
NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_.])" + NUMBER + r"(?![A-Za-z0-9_.])")
SCI_CHAR_RE = re.compile("[" + re.escape("".join(GREEK) + "ÅÅµ±×·−⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻") + "]")


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normal(text):
    """Conservative display normalization: NFC, spacing, Unicode minus only."""
    text = unicodedata.normalize("NFC", text).replace("−", "-")
    text = re.sub(r"\s*([=/,×·*^_{}()\[\]+<>-])\s*", r"\1", text)
    text = re.sub(r"(?<=\d)\s+(?=[A-Za-zÅ°µμ])", "", text)
    return re.sub(r"\s+", " ", text).strip()


def latex_display(text):
    """Recognize a small display subset, never infer mathematical equivalence."""
    text = unicodedata.normalize("NFC", text)
    aliases = {name: symbol for symbol, name in GREEK.items()}
    aliases.update({"AA": "Å", "angstrom": "Å", "times": "×", "cdot": "·", "pm": "±"})
    text = re.sub(r"\\([A-Za-z]+)", lambda m: aliases.get(m[1], m[0]), text)
    text = re.sub(r"\\(?:,|;|!| )", " ", text)
    text = re.sub(r"\\[()[\]]|\$", "", text)
    # Unwrap only these presentation commands, not arbitrary TeX syntax.
    for _ in range(4):
        updated = re.sub(r"\\(?:mathrm|text|mathit|textrm)\{([^{}]*)\}", r"\1", text)
        if updated == text:
            break
        text = updated
    text = re.sub(r"([_^])\{([A-Za-z0-9+\-−]+)\}", r"\1\2", text)
    text = re.sub(r"\\SI\{([^{}]*)\}\{([^{}]*)\}", r"\1 \2", text)
    return normal(text)


def contains(body, literal):
    if not literal:
        return False
    pattern = re.escape(literal)
    if re.fullmatch(NUMBER, literal):
        return re.search(r"(?<![A-Za-z0-9_.])" + pattern + r"(?![0-9.]|[eE][+\-−]?\d)", body) is not None
    if literal[0].isascii() and literal[0].isalpha():
        pattern = r"(?<![A-Za-z_])" + pattern
    if literal[-1].isascii() and literal[-1].isalpha():
        pattern += r"(?![A-Za-z_])"
    return re.search(pattern, body) is not None


def match_kind(body, literal):
    if contains(body, literal):
        return "exact_literal"
    if contains(normal(body), normal(literal)):
        return "spacing_or_unicode_equivalent"
    if contains(latex_display(body), latex_display(literal)):
        return "representation_variant_requires_review"
    return "not_found"


def load_document(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    value = None
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    elif text.lstrip().startswith("{"):
        try:
            candidate = json.loads(text)
            if isinstance(candidate, dict) and "text" in candidate:
                value = candidate
        except json.JSONDecodeError:
            pass
    if value is None and path.suffix.lower() != ".json":
        return {"text": text, "changes": "", "pending": ""}, "plain_text"
    if not isinstance(value, dict) or not isinstance(value.get("text"), str):
        raise ValueError("Writer JSON must be an object with a string text field: " + str(path))
    sections = {"text": value["text"]}
    for name in ("changes", "pending"):
        items = value.get(name, [])
        if not isinstance(items, list) or any(not isinstance(x, str) for x in items):
            raise ValueError(name + " must be an array of strings: " + str(path))
        sections[name] = "\n".join(items)
    return sections, "writer_json"


def load_protected(path):
    if path is None:
        return []
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if isinstance(value, dict):
        value = value.get("literals")
    if not isinstance(value, list):
        raise ValueError("protected-json must be an array or {\"literals\": [...]}.")
    result = []
    for item in value:
        if isinstance(item, str):
            item = {"literal": item}
        if (not isinstance(item, dict) or not isinstance(item.get("literal"), str)
                or not item["literal"].strip() or not isinstance(item.get("note", ""), str)):
            raise ValueError("Each protected entry needs a nonempty literal and optional string note.")
        if set(item) - {"literal", "note"}:
            raise ValueError("Unsupported protected entry field; only literal and note are allowed.")
        if item["literal"] not in [x["literal"] for x in result]:
            result.append({"literal": item["literal"], "note": item.get("note", "")})
    return result


def extract(text):
    text = unicodedata.normalize("NFC", text)
    numeric_text = normal(text)
    return {
        "quantities": Counter(m[0] for m in QUANTITY_RE.finditer(numeric_text)),
        "numbers": Counter(m[0] for m in NUMBER_RE.finditer(numeric_text)),
        "scientific_characters": Counter(SCI_CHAR_RE.findall(text.replace("−", "-"))),
    }


def audit(source, draft, protected=(), min_han=None, max_han=None):
    """Pure function for documents already split into text/changes/pending."""
    if any(x is not None and (type(x) is not int or x < 0) for x in (min_han, max_han)):
        raise ValueError("Han limits must be nonnegative integers.")
    if min_han is not None and max_han is not None and min_han > max_han:
        raise ValueError("min-han exceeds max-han.")
    findings = []
    literal_checks = []
    for entry in protected:
        literal = entry["literal"]
        src_kind = match_kind(source["text"], literal)
        dst_kind = match_kind(draft["text"], literal)
        elsewhere = {name: match_kind(draft[name], literal) for name in ("changes", "pending")}
        row = dict(entry, source_text_match=src_kind, draft_text_match=dst_kind,
                   other_fields=elsewhere, scope="text_only")
        literal_checks.append(row)
        if src_kind == "not_found":
            findings.append({"code": "protected_literal_not_in_source_text", "field": "text", "literal": literal,
                             "meaning": "Check the protection specification/source scope; no scientific error is inferred."})
        if dst_kind in ("not_found", "representation_variant_requires_review"):
            code = "protected_literal_not_found_in_text" if dst_kind == "not_found" else "protected_representation_variant"
            findings.append({"code": code, "field": "text", "literal": literal, "other_fields": elsewhere})
        for symbol, spelling in GREEK.items():
            if symbol in unicodedata.normalize("NFC", literal) and dst_kind == "not_found" and re.search(r"(?<![A-Za-z])" + spelling + r"(?![A-Za-z])", draft["text"]):
                findings.append({"code": "greek_spelling_suspected", "field": "text", "literal": literal, "symbol": symbol, "spelling": spelling})
        if "Å" in unicodedata.normalize("NFC", literal) and dst_kind == "not_found":
            candidate = unicodedata.normalize("NFC", literal).replace("Å", "A")
            if match_kind(draft["text"], candidate) != "not_found":
                findings.append({"code": "angstrom_to_ascii_A_suspected", "field": "text", "literal": literal, "candidate": candidate})
    comparisons = {}
    for field in ("text", "changes", "pending"):
        before, after = extract(source[field]), extract(draft[field])
        comparison = {}
        for category in before:
            missing = sorted(before[category].keys() - after[category].keys())
            added = sorted(after[category].keys() - before[category].keys())
            comparison[category] = {"source_counts": dict(sorted(before[category].items())),
                                    "draft_counts": dict(sorted(after[category].items())),
                                    "absent_tokens": missing, "new_tokens": added}
            for direction, values, target in [("absent", missing, draft[field]), ("new", added, source[field])]:
                for token in values:
                    variant = match_kind(target, token) == "representation_variant_requires_review"
                    findings.append({"code": "automatic_representation_variant" if variant else "automatic_" + direction + "_token",
                                     "field": field, "category": category, "literal": token,
                                     "origin": "heuristic_only", "direction": direction})
        comparisons[field] = comparison
    # Deliberately matches the existing evaluation's BMP Han-count convention.
    han = sum("\u4e00" <= char <= "\u9fff" for char in draft["text"])
    within = (min_han is None or han >= min_han) and (max_han is None or han <= max_han)
    if not within:
        findings.append({"code": "text_han_outside_requested_range", "field": "text", "count": han,
                         "min_han": min_han, "max_han": max_han})
    for finding in findings:
        finding["severity"] = "review_only"
    return {
        "schema_version": VERSION,
        "status": "review_required" if findings else "no_lexical_difference_detected",
        "review_required": bool(findings), "needs_human_or_model_check": True,
        "scientific_correctness": "not_assessed", "semantic_preservation": "not_assessed",
        "semantic_paragraph_count": "not_assessed",
        "protected_literal_checks": literal_checks, "field_comparisons": comparisons,
        "text_han_count": {"count": han, "definition": "Unicode U+4E00..U+9FFF; text field only; same convention as existing evaluator",
                           "min_han": min_han, "max_han": max_han,
                           "range_requested": min_han is not None or max_han is not None,
                           "within_requested_range": within if min_han is not None or max_han is not None else None},
        "findings": findings,
        "limitations": [
            "No finding means only that these lexical checks found no difference, never semantic preservation or scientific correctness.",
            "Presence of a literal anywhere in text does not prove correct object, context, units, condition, negation or occurrence-level preservation.",
            "changes and pending never compensate for a missing literal in text; their differences are reported separately.",
            "Automatic extraction is a small heuristic, including repeated-count inventories; absent/new types are alerts, not hard defects.",
            "NFC and conservative spacing/minus normalization are allowed; Å is never normalized to A. LaTeX aliases require review, not automatic rejection.",
            "No mathematical equivalence, converted-unit equivalence, scientific synonym, natural-paragraph or prose-quality certification is performed.",
            "Han counting uses U+4E00..U+9FFF only, excludes other CJK blocks, and counts text literally (including Han inside formulas).",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--draft", required=True)
    parser.add_argument("--protected-json")
    parser.add_argument("--min-han", type=int)
    parser.add_argument("--max-han", type=int)
    parser.add_argument("--output", help="JSON report path; omitted means stdout. Inputs cannot be overwritten.")
    args = parser.parse_args(argv)
    try:
        inputs = [Path(p).resolve() for p in (args.source, args.draft, args.protected_json) if p]
        if args.output and Path(args.output).resolve() in inputs:
            raise ValueError("Output path must not overwrite an input file.")
        source, source_format = load_document(args.source)
        draft, draft_format = load_document(args.draft)
        result = audit(source, draft, load_protected(args.protected_json), args.min_han, args.max_han)
        result["inputs"] = {name: {"path": str(Path(path).resolve()), "sha256": sha(path), "format": fmt}
                            for name, path, fmt in [("source", args.source, source_format), ("draft", args.draft, draft_format)]}
        if args.protected_json:
            result["inputs"]["protected"] = {"path": str(Path(args.protected_json).resolve()), "sha256": sha(args.protected_json)}
        payload = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        if args.output:
            Path(args.output).write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0
    except (OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "input_error", "needs_human_or_model_check": True, "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
