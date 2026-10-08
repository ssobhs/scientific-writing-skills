"""Measure an explicitly separated UTF-8 body file; never infer its boundaries.

Example: python measure_text.py --body body.txt --unit han --minimum 1800 --maximum 2200
Counts are form evidence only, not a scientific or writing-quality judgment.
"""
from pathlib import Path
import argparse, hashlib, json, re

def measure(text, unit):
    if unit == 'han':
        return len(re.findall(r'[\u4e00-\u9fff]', text))
    if unit == 'nonspace':
        return len(re.sub(r'\s', '', text))
    raise ValueError('Use han or nonspace explicitly.')

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--body',required=True,type=Path,help='正文单独文件；先排除标题和文后说明，程序不猜边界')
    ap.add_argument('--unit',required=True,choices=['han','nonspace'])
    ap.add_argument('--minimum',type=int)
    ap.add_argument('--maximum',type=int)
    args=ap.parse_args()
    if args.minimum is not None and args.minimum<0:ap.error('minimum must be nonnegative')
    if args.maximum is not None and args.maximum<0:ap.error('maximum must be nonnegative')
    if args.minimum is not None and args.maximum is not None and args.minimum>args.maximum:ap.error('minimum exceeds maximum')
    raw=args.body.read_bytes();text=raw.decode('utf-8-sig');count=measure(text,args.unit)
    position='not_specified'
    if args.minimum is not None or args.maximum is not None:
        position='below' if args.minimum is not None and count<args.minimum else 'above' if args.maximum is not None and count>args.maximum else 'within'
    print(json.dumps({'body_path':str(args.body.resolve()),'body_sha256':hashlib.sha256(raw).hexdigest(),
                      'unit':args.unit,'count':count,'minimum':args.minimum,'maximum':args.maximum,'position':position,
                      'counting_rule':'han counts U+4E00-U+9FFF only; nonspace counts all non-whitespace Unicode code points',
                      'limits':'Caller must confirm body boundaries and range interpretation; this does not assess scientific accuracy or sufficient analysis.'},ensure_ascii=False))

if __name__=='__main__':main()
