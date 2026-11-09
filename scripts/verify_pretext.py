#!/usr/bin/env python3
"""Check conversion structure and HTML behavior; optionally exercise the watcher."""
from pathlib import Path
import argparse, hashlib, json, re, sys, time, urllib.request
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from generate_pretext import split_chunks, strip_comments, group

def verify():
    root=ET.parse(ROOT/'PreTeXt/source/main.ptx')
    report=json.loads((ROOT/'PreTeXt/conversion-report.json').read_text())
    mapping=json.loads((ROOT/'PreTeXt/source-map.json').read_text())
    source=[]; expected_sections=[]; image_count=0
    for p in sorted((ROOT/'Notes').glob('Chap*/*-lectures.tex')):
        body=strip_comments(p.read_text().split(r'\begin{document}')[1].split(r'\end{document}')[0]);count=0
        chapter=int(re.search(r'Chap(\d+)',str(p))[1])
        image_count+=len(re.findall(r'\\includegraphics\b',body))+len(re.findall(r'\\begin\{tikzpicture\}',body))
        for kind,text in split_chunks(body):
            if kind in ('chaptertitle','topic'):continue
            if kind=='sectiontitle': number,_=group(text,0);expected_sections.append(number);continue
            count+=1;source.append((chapter,kind,count))
    assert source==[(x['chapter'],x['kind'],x['number']) for x in mapping]
    acts=root.findall('.//activity')
    expected_activities=sum(kind=='activity' for _,kind,_ in source)
    assert len(acts)==report['activities']==expected_activities
    assert image_count==report['images']==len(root.findall('.//image'))
    assert len(expected_sections)==report['sections']
    ids={x.get('{http://www.w3.org/XML/1998/namespace}id') for x in root.iter()}
    for xref in root.findall('.//xref'):assert xref.get('ref') in ids
    assert len(root.findall('.//xref'))==sum(len(re.findall(r'\\ref\{',strip_comments(p.read_text().split(r'\begin{document}')[1]))) for p in (ROOT/'Notes').glob('Chap*/*-lectures.tex'))
    for a in acts:
        assert len(a.findall('solution'))==1 and len(a.findall('statement'))==1
        assert ''.join(a.find('solution').itertext()).strip()
    for m in mapping:
        section=root.find('.//section[@{http://www.w3.org/XML/1998/namespace}id="section-'+m['section'].replace('.','-')+'"]')
        page=ROOT/'PreTeXt/output/web'/('section-'+m['section'].replace('.','-')+'.html')
        assert page.exists()
        html=page.read_text()
        ident=re.escape(m['id'])
        heading=re.search(r'<article[^>]*id="'+ident+r'".*?<h\d[^>]*>(.*?)</h\d>',html,re.S)
        assert heading, m
        n=re.search(r'class="codenumber">([^<]*)',heading[1])
        assert n and n[1]==str(m['number']),(m,n[1] if n else None)
    details=0
    for number in expected_sections:
        page=ROOT/'PreTeXt/output/web'/('section-'+number.replace('.','-')+'.html')
        html=page.read_text()
        solutions=re.findall(r'<details\b[^>]*class="[^"]*solution [^"]*"[^>]*>',html)
        details+=len(solutions)
        assert all(not re.search(r'\bopen(?:=|\s|>)',s) for s in solutions)
        assert 'PTXPLACEHOLDER' not in html and 'PTXENDANSWER' not in html
        assert not re.search(r'\[activity-[^]]+\]',html)
        for src in re.findall(r'<(?:img|script)[^>]*\bsrc="([^"]+)"',html):
            if src.startswith(('http:','https:','data:','//')):continue
            assert (page.parent/src.split('?')[0]).is_file(),src
    assert details==expected_activities,details
    try:
        from lxml import etree
        from pretext import resources
    except ImportError: print('Schema validation available when using the Python installation containing PreTeXt/lxml.')
    else:
        schema=etree.RelaxNG(etree.parse(str(resources.resource_base_path()/'core/schema/pretext.rng')))
        assert schema.validate(etree.parse(str(ROOT/'PreTeXt/source/main.ptx'))),schema.error_log
        print('Official PreTeXt schema: PASS')
    print(f'PASS: {report["chapters"]} chapters, {report["sections"]} section pages, {expected_activities} collapsed solutions, source block numbering, references, figures, and local assets.')

def status(url):return json.load(urllib.request.urlopen(url+'/__preview_status'))

def wait_build(url,previous,timeout=150):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        s=status(url)
        if s['error'] and not s['building'] and time.monotonic()>deadline-timeout+4:raise AssertionError(s['error'])
        if s['version']>previous and not s['building']:return s
        time.sleep(1)
    raise TimeoutError('Automatic build did not finish')

def watcher_test(url):
    path=ROOT/'Notes/Chap3/Chap3-lectures.tex'
    before=path.read_bytes();digest=hashlib.sha256(before).hexdigest()
    marker=b'\n% Temporary PreTeXt watcher verification; removed automatically.\n'
    initial=status(url)
    while initial['building']:time.sleep(1);initial=status(url)
    try:
        path.write_bytes(before+marker)
        built=wait_build(url,initial['version'])
        print('TeX save triggered automatic HTML rebuild: PASS',flush=True)
    finally:
        current=path.read_bytes()
        if current.endswith(marker):path.write_bytes(current[:-len(marker)])
        else:raise AssertionError('Source changed during verification; inspect the temporary comment')
    wait_build(url,built['version'])
    assert hashlib.sha256(path.read_bytes()).hexdigest()==digest
    print('Original TeX restored byte-for-byte; rebuild after restore: PASS',flush=True)
    verify()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--watch-url');args=parser.parse_args()
    if args.watch_url:watcher_test(args.watch_url)
    else:verify()
