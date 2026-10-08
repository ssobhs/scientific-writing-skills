"""Read-only glyph evidence; deliberately does not infer scientific semantics."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def page_numbers(spec, count):
    """Explicit physical page numbers, 1-based, never printed page labels."""
    values = []
    for item in spec.split(','):
        ends = item.split('-')
        if len(ends) == 1:
            values.append(int(ends[0]))
        elif len(ends) == 2:
            first, last = map(int, ends)
            if first > last:
                raise ValueError('Page range must be ascending')
            values.extend(range(first, last + 1))
        else:
            raise ValueError('Invalid page range')
    if not values or any(p < 1 or p > count for p in values):
        raise ValueError(f'Physical page numbers must be between 1 and {count}')
    return list(dict.fromkeys(values))


def collect(source, pages=None, bbox=None):
    source = Path(source).resolve(strict=True)
    before = sha256(source)
    result = {
        'schema': 'word-native-math.source-evidence.v1',
        'source': str(source), 'source_sha256_before': before,
        'semantic_recognition': 'not_performed',
        'warning': 'Glyph geometry/font evidence is not a verified transcription. Do not infer subscript, superscript, italic/bold semantics, or unclear digits from size/baseline/font names alone.',
    }
    if source.suffix.lower() == '.pdf':
        if not pages:
            raise ValueError('PDF requires explicit --pages (physical, 1-based)')
        import pdfplumber
        result.update(kind='pdf', reader='pdfplumber', reader_version=pdfplumber.__version__,
                      coordinate_system='PDF points; x from left; top/bottom from top; original page coordinates; bbox=(x0,top,x1,bottom)', pages=[])
        fields = ('text', 'x0', 'x1', 'top', 'bottom', 'y0', 'y1', 'doctop', 'size', 'fontname', 'upright', 'adv', 'width', 'height', 'matrix')
        with pdfplumber.open(source) as pdf:
            result['physical_page_count'] = len(pdf.pages)
            for number in page_numbers(pages, len(pdf.pages)):
                page = pdf.pages[number - 1]
                selected = page
                if bbox is not None:
                    if len(bbox) != 4 or not all(math.isfinite(v) for v in bbox):
                        raise ValueError('Crop coordinates must be four finite numbers')
                    x0, top, x1, bottom = bbox
                    if x0 >= x1 or top >= bottom:
                        raise ValueError('Crop must have positive width and height')
                    selected = page.crop(tuple(bbox), strict=True)
                chars = [{k: char[k] for k in fields if k in char} for char in selected.chars]
                # Full original glyphs remain available: crop can clip bbox values.
                originals = [{k: char[k] for k in fields if k in char} for char in page.chars]
                text = selected.extract_text() or ''
                result['pages'].append({
                    'physical_page_number_1based': number,
                    'width_pt': page.width, 'height_pt': page.height,
                    'rotation': page.rotation, 'original_page_bbox': list(page.bbox),
                    'requested_crop_bbox': list(bbox) if bbox is not None else None,
                    'selected_bbox': list(selected.bbox),
                    'extracted_text': text, 'full_page_extracted_text': page.extract_text() or '',
                    'chars': chars, 'full_page_chars': originals,
                    'text_layer_status': 'characters_available_unverified' if chars else 'no_characters_in_selected_region',
                    'next_action': 'Render and visually compare glyphs, roles, and complete symbol spans; use OCR only as an unverified aid. Empty or garbled extracted text does not mean empty content.',
                })
    else:
        if pages or bbox is not None:
            raise ValueError('--pages/--bbox apply only to PDF; preserve original image coordinates')
        from PIL import Image
        with Image.open(source) as img:
            result.update(kind='image', format=img.format, width_px=img.width,
                          height_px=img.height, mode=img.mode, frame_count=getattr(img, 'n_frames', 1))
            img.verify()
        result.update(read_status='image_container_verified', ocr_status='not_performed',
                      recognized_text=None, next_action='Inspect the image visually; ambiguous glyphs require a clearer source or explicit confirmation. No text has been recognized by this tool.')
    after = sha256(source)
    result.update(source_sha256_after=after, source_unchanged=(before == after))
    if before != after:
        raise RuntimeError('Source changed during inspection; evidence not saved')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--output', required=True, type=Path, help='New JSON path; existing files are never overwritten')
    parser.add_argument('--pages', help='PDF physical pages: e.g. 1,3-4 (1-based)')
    parser.add_argument('--bbox', nargs=4, type=float, metavar=('X0', 'TOP', 'X1', 'BOTTOM'))
    args = parser.parse_args()
    try:
        source = args.source.resolve(strict=True)
        output = args.output.resolve()
        if output == source or output.exists():
            raise ValueError('Output must be a new path distinct from source')
        result = collect(source, args.pages, args.bbox)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        print(json.dumps({'output': str(output), 'kind': result['kind'], 'source_unchanged': True,
                          'semantic_recognition': 'not_performed'}, ensure_ascii=False))
    except Exception as exc:
        parser.exit(2, f'ERROR: {type(exc).__name__}: {exc}\n')


if __name__ == '__main__':
    main()
