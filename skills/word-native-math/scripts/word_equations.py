"""Insert native, editable OMML from explicit LaTeX using external Pandoc.

Only marked equation placeholders are replaced; the existing thesis is not
round-tripped through Pandoc. No images or plain-LaTeX fallback is accepted.
"""
from __future__ import annotations
import argparse,copy,hashlib,json,os,re,shutil,subprocess,tempfile,zipfile
from pathlib import Path
from lxml import etree as E

NS={'w':'http://schemas.openxmlformats.org/wordprocessingml/2006/main','m':'http://schemas.openxmlformats.org/officeDocument/2006/math'}
W='{'+NS['w']+'}';M='{'+NS['m']+'}'
PARSER=E.XMLParser(resolve_entities=False,no_network=True)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def prescript_fragment(spec):
    """Explicit native left sub/superscripts; no inference from isotope numbers."""
    for key in ('base','sub','sup'):
        if not isinstance(spec.get(key),str) or not spec[key]:raise ValueError('prescript requires nonempty base, sub, sup strings')
    math=E.Element(M+'oMath',nsmap=NS);pre=E.SubElement(math,M+'sPre')
    for tag,value in [('sub',spec['sub']),('sup',spec['sup']),('e',spec['base'])]:
        arg=E.SubElement(pre,M+tag);r=E.SubElement(arg,M+'r')
        if tag!='e' or spec.get('upright',True):
            pr=E.SubElement(r,M+'rPr');E.SubElement(pr,M+'sty').set(M+'val','p')
        pr=E.SubElement(r,W+'rPr');font=E.SubElement(pr,W+'rFonts')
        for attr in ('ascii','hAnsi','cs'):font.set(W+attr,'Cambria Math')
        E.SubElement(r,M+'t').text=value
    return math
def math_fragment(latex,pandoc,scratch):
    """Convert one explicit expression, rejecting warnings and non-OMML output."""
    if not isinstance(latex,str) or not latex.strip() or '$' in latex:
        raise ValueError('Supply one LaTeX expression without $ delimiters')
    scratch=Path(scratch).resolve();scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='omml-',dir=scratch) as tmp:
        assert Path(tmp).resolve().is_relative_to(scratch)
        dest=Path(tmp)/'fragment.docx'
        command=[str(pandoc),'--sandbox','--from=markdown+tex_math_dollars','--to=docx','--fail-if-warnings','--output',str(dest)]
        run=subprocess.run(command,input='$$\n'+latex+'\n$$\n',text=True,encoding='utf-8',capture_output=True,timeout=60)
        if run.returncode:
            raise ValueError('Pandoc rejected expression: '+run.stderr.strip())
        with zipfile.ZipFile(dest) as z:root=E.fromstring(z.read('word/document.xml'),PARSER)
        items=root.xpath('//m:oMath',namespaces=NS)
        if len(items)!=1 or not items[0].xpath('.//m:t[text()]',namespaces=NS):
            raise ValueError('Pandoc did not produce exactly one nonempty OMML equation')
        result=copy.deepcopy(items[0])
        # Keep mathematical normal-text/italic distinctions from texmath.
        # An explicit local math font does not modify other document equations.
        for r in result.findall('.//'+M+'r'):
            pr=r.find(W+'rPr')
            if pr is None:
                pr=E.Element(W+'rPr');rp=r.find(M+'rPr');r.insert(1 if rp is not None else 0,pr)
            fonts=pr.find(W+'rFonts')
            if fonts is None:fonts=E.Element(W+'rFonts');pr.insert(0,fonts)
            for attr in ('ascii','hAnsi','cs'):fonts.set(W+attr,'Cambria Math')
        return result,run.stderr

def append_equation(paragraph,latex,pandoc,scratch,display=False):
    """Append to a python-docx Paragraph; its existing text is untouched."""
    math,_=math_fragment(latex,pandoc,scratch)
    if display:
        if any(x.tag!=W+'pPr' for x in paragraph._p):
            raise ValueError('Display equations require an empty paragraph')
        wrapper=E.Element(M+'oMathPara');wrapper.append(math);paragraph._p.append(wrapper)
    else:paragraph._p.append(math)
    return math

def _text(r):return ''.join(r.xpath('./w:t/text()',namespaces=NS))
def _text_only(r):return r.tag==W+'r' and all(x.tag in (W+'rPr',W+'t') for x in r)
def _split_run(r,text):
    n=copy.deepcopy(r)
    for child in list(n):
        if child.tag!=W+'rPr':n.remove(child)
    t=E.SubElement(n,W+'t');t.set('{http://www.w3.org/XML/1998/namespace}space','preserve');t.text=text
    return n

def _protected_paragraphs(root):
    marked=set();depth=0
    for node in root.iter():
        if node.tag==W+'p' and depth:marked.add(node)
        if node.tag==W+'fldChar':
            para=next((a for a in node.iterancestors() if a.tag==W+'p'),None)
            if para is not None:marked.add(para)
            kind=node.get(W+'fldCharType')
            if kind=='begin':depth+=1
            elif kind=='end':depth=max(0,depth-1)
    for p in root.xpath('//w:p',namespaces=NS):
        for node in list(p.iter())+list(p.iterancestors()):
            if not isinstance(node.tag,str) or E.QName(node).namespace!=NS['w']:continue
            name=E.QName(node).localname
            if name in ('sdt','fldSimple','fldChar','instrText','delInstrText','ins','del','moveFrom','moveTo','cellIns','cellDel','cellMerge') or name.endswith('Change') or name.startswith(('moveFromRange','moveToRange')):
                marked.add(p);break
    return marked

def replace_equations(source,plan_path,output,pandoc,scratch,report):
    source=Path(source).resolve();output=Path(output).resolve();report=Path(report).resolve()
    if source==output or output.exists():raise ValueError('Use a new output path; input is preserved')
    if report.exists() or report in (source,output):raise ValueError('Use a separate new report path')
    spec=json.loads(Path(plan_path).read_text(encoding='utf-8-sig'))
    cases=spec.get('equations',spec.get('cases'))
    if not isinstance(cases,list) or not cases:raise ValueError('equations must be a nonempty list')
    with zipfile.ZipFile(source) as z:
        infos=z.infolist()
        if len({x.filename for x in infos})!=len(infos):raise ValueError('Duplicate ZIP parts are unsupported')
        data={x.filename:z.read(x) for x in infos};comment=z.comment
    root=E.fromstring(data['word/document.xml'],PARSER)
    if root.getroottree().docinfo.doctype:raise ValueError('DTD is not supported in DOCX XML')
    protected=_protected_paragraphs(root)
    tasks=[];used=set()
    for case in cases:
        token=case['placeholder'];display=case.get('display',True)
        if not token or not isinstance(display,bool):raise ValueError('Invalid placeholder or display flag')
        found=[]
        for p in root.xpath('//w:p',namespaces=NS):
            text=''.join(p.xpath('.//w:t/text()',namespaces=NS))
            if token not in text:continue
            if p in protected:
                raise ValueError('Placeholder is in a protected field/revision/content control')
            if display:
                if text!=token or any(x.tag not in (W+'pPr',W+'r') for x in p) or not all(_text_only(r) for r in p.findall(W+'r')):
                    raise ValueError('Display placeholder must be alone in a plain paragraph')
                found.append((p,None))
            else:
                if text.count(token)!=1:
                    raise ValueError('Inline placeholder must occur exactly once in the whole paragraph')
                matches=[r for r in p.findall(W+'r') if _text_only(r) and token in _text(r)]
                if len(matches)!=1 or _text(matches[0]).count(token)!=1:
                    raise ValueError('Inline placeholder must occur once within one direct text run')
                found.append((p,matches[0]))
        if len(found)!=case.get('expected_count',1):
            raise ValueError('Placeholder count mismatch: '+token)
        for p,r in found:
            identity=p if display else r
            if identity in used:raise ValueError('Overlapping equation targets')
            used.add(identity);tasks.append((case,p,r))
    # Convert everything before mutating the document or writing any output.
    math_cache={}
    for case,_,_ in tasks:
        if ('latex' in case)==('prescript' in case):raise ValueError('Specify exactly one of latex or prescript')
        key=json.dumps({k:case[k] for k in ('latex','prescript') if k in case},sort_keys=True)
        if key not in math_cache:
            math_cache[key]=prescript_fragment(case['prescript']) if 'prescript' in case else math_fragment(case['latex'],pandoc,scratch)[0]
        m=math_cache[key]
        for required in case.get('expected_omml',[]):
            if not m.xpath('.//'+required,namespaces=NS):raise ValueError('Missing requested OMML structure '+required)
    records=[]
    for case,p,r in tasks:
        key=json.dumps({k:case[k] for k in ('latex','prescript') if k in case},sort_keys=True)
        math=copy.deepcopy(math_cache[key]);token=case['placeholder']
        if r is None:
            for child in list(p):
                if child.tag!=W+'pPr':p.remove(child)
            wrapper=E.SubElement(p,M+'oMathPara');wrapper.append(math)
        else:
            prefix,suffix=_text(r).split(token);idx=p.index(r);p.remove(r)
            new=([_split_run(r,prefix)] if prefix else [])+[math]+([_split_run(r,suffix)] if suffix else [])
            for offset,n in enumerate(new):p.insert(idx+offset,n)
        records.append({'placeholder':token,'source':{k:case[k] for k in ('latex','prescript') if k in case},'display':r is None,'structures':sorted(set(E.QName(x).localname for x in math.iter() if E.QName(x).namespace==NS['m']))})
    data['word/document.xml']=E.tostring(root,encoding='UTF-8',xml_declaration=True,standalone=True)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x') as z:
        z.comment=comment
        for info in infos:z.writestr(info,data[info.filename])
    result={'input':str(source),'input_sha256':sha(source),'output':str(output),'output_sha256':sha(output),'equations':records,'pandoc':str(pandoc),'changed_parts':['word/document.xml'],'representation':'native OMML, no image fallback'}
    report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('input');p.add_argument('plan');p.add_argument('output');p.add_argument('--pandoc',default=os.environ.get('PANDOC_PATH') or shutil.which('pandoc'));p.add_argument('--scratch');p.add_argument('--report',required=True)
    a=p.parse_args()
    if not a.pandoc:p.error('Pandoc is required; pass --pandoc or set PANDOC_PATH')
    scratch=Path(a.scratch) if a.scratch else Path(a.output).resolve().parent/'_equation_scratch'
    r=replace_equations(a.input,a.plan,a.output,a.pandoc,scratch,a.report)
    print(json.dumps({'output':r['output'],'equations':len(r['equations'])},ensure_ascii=False))
if __name__=='__main__':main()
