#!/usr/bin/env python3
"""Generate PreTeXt from the original lecture TeX; requires pandoc on PATH.

Pandoc parses LaTeX paragraphs/lists/math. This adapter supplies the course's
semantic commands, removes print layout, and relocates activity answers.
Unknown constructs fail rather than silently dropping lecture material.
"""
from pathlib import Path
import re, json, subprocess, shutil, html, hashlib, tempfile, xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'PreTeXt'
ESC = html.escape
KINDS = 'activity theorem corollary lemma fact note definition remark'.split()
STATS = {'chapters': 0, 'sections': 0, 'activities': 0, 'solutions': 0, 'blanks': 0, 'images': 0, 'tikz_figures': 0}

def group(s, i, opening='{', closing='}'):
    while i < len(s) and s[i].isspace(): i += 1
    if i >= len(s) or s[i] != opening: raise ValueError(f'Expected {opening}: {s[i:i+100]}')
    start = i + 1; depth = 1; i += 1
    while i < len(s):
        if s[i] == '\\': i += 2; continue
        if s[i] == opening: depth += 1
        if s[i] == closing:
            depth -= 1
            if not depth: return s[start:i], i+1
        i += 1
    raise ValueError('Unbalanced TeX group')

def strip_comments(s): return re.sub(r'(?<!\\)%[^\n]*', '', s)

def math_at(s, stop):
    """Track math delimiters outside command argument groups."""
    i = 0; mode = None
    while i < stop:
        if s[i] == '\\':
            if s[i:i+2] in ('\\(', '\\['): mode = s[i:i+2]; i += 2; continue
            if s[i:i+2] in ('\\)', '\\]'): mode = None; i += 2; continue
            m = re.match(r'\\(?:answer|shortanswer|fillin|underline)\b', s[i:])
            if m:
                j = i+len(m[0])
                while j<len(s) and s[j].isspace(): j+=1
                if s[j:j+1]=='[': _,j=group(s,j,'[',']')
                _,i=group(s,j); continue
            i += 2; continue
        if s[i] == '$':
            delim = '$$' if s[i:i+2]=='$$' else '$'
            mode = None if mode == delim else delim; i += len(delim); continue
        i += 1
    return mode is not None

class Converter:
    def __init__(self, chapter, macros):
        self.chapter=chapter; self.macros=macros; self.placeholders={}; self.token_count=0

    def token(self, xml):
        self.token_count+=1; key=f'PTXPLACEHOLDER{self.token_count:05d}'; self.placeholders[key]=xml
        return r'\texttt{'+key+'}'

    def annotations(self, s, activity=False):
        answers=[]; count=0; last=0; parts=[]
        for m in re.finditer(r'\\(answer|shortanswer|fillin|underline)\b',s):
            if m.start()<last: continue
            j=m.end()
            while j<len(s) and s[j].isspace(): j+=1
            if s[j:j+1]=='[': _,j=group(s,j,'[',']')
            body,end=group(s,j)
            parts.append(s[last:m.start()]); kind=m[1]; inmath=math_at(s,m.start())
            if activity:
                if kind=='answer':
                    answers.append(('Solution part', body)); parts.append(r'\texttt{PTXENDANSWER}')
                else:
                    count+=1; STATS['blanks']+=1
                    # A shortanswer inside $...$ has math content without its own delimiters.
                    ans=('$'+body+'$') if inmath else body
                    answers.append((f'Blank {count}',ans))
                    parts.append((r'\text{[Blank '+str(count)+']}') if inmath else self.token('<fillin characters="12"/><em> ('+str(count)+')</em>'))
            else:
                if kind=='answer':
                    parts.append('\n\n'+self.token('</p><p><em>Answer.</em></p>'+self.blocks(self.parse(body))+'<p>')+'\n\n')
                elif inmath: parts.append(r'\boldsymbol{'+body+'}')
                else: parts.append(r'\textbf{'+body+'}')
            last=end
        parts.append(s[last:]); return ''.join(parts), answers

    def tikz_image(self, match):
        source=match[0]
        digest=hashlib.sha256(source.encode()).hexdigest()[:16]
        directory=OUT/'assets'/'images'; directory.mkdir(parents=True,exist_ok=True)
        filename=f'c{self.chapter}-tikz-{digest}.svg'; target=directory/filename
        if not target.exists():
            for executable in ('latex','dvisvgm'):
                if not shutil.which(executable): raise RuntimeError(f'{executable} is required to render TikZ figures')
            with tempfile.TemporaryDirectory(prefix='pretext-tikz-') as tmp:
                folder=Path(tmp)
                tex=r'\documentclass[tikz,border=4pt]{standalone}'+r'\usepackage{amsmath}'+r'\begin{document}'+source+r'\end{document}'
                (folder/'figure.tex').write_text(tex)
                for command in ([shutil.which('latex'),'-interaction=nonstopmode','-halt-on-error','figure.tex'],
                                [shutil.which('dvisvgm'),'--no-fonts','--exact-bbox','--output=figure.svg','figure.dvi']):
                    result=subprocess.run(command,cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
                    if result.returncode: raise RuntimeError('TikZ rendering failed:\n'+result.stdout[-6000:])
                shutil.copy2(folder/'figure.svg',target)
        STATS['images']+=1; STATS['tikz_figures']+=1
        xml='<image source="images/'+filename+'" width="100%"><shortdescription>First-row cofactor expansion of a 3 by 3 matrix. Each panel crosses out row 1 and column j, highlights the remaining 2 by 2 minor, and shows the signed term. The three signs are plus, minus, plus.</shortdescription></image>'
        return '\n\n'+self.token('</p>'+xml+'<p>')+'\n\n'

    def prep(self, s):
        s=re.sub(r'\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}',self.tikz_image,s,flags=re.S)
        s=re.sub(r'\\(?:newpage|bigskip|medskip|smallskip|noindent|centering|small)\b','',s)
        s=re.sub(r'\\vspace\*?\s*\{[^}]*\}','',s)
        s=re.sub(r'\\begin\{minipage\}(?:\[[^]]*\])?\{[^}]*\}', '', s)
        s=s.replace(r'\end{minipage}','')
        s=s.replace(r'\begin{framed}','').replace(r'\end{framed}','')
        for name,label in {'proof':'Why is it true?', 'question':'Question:', 'notice':'Notice:', 'setup':'Set-up:', 'idea':'Idea:', 'warning':'Warning:'}.items():
            s=re.sub(r'\\'+name+r'\b',lambda m:r'\textbf{'+label+'} ',s)
        # TeX line breaks in prose become paragraph boundaries in Pandoc.
        return s

    def parse(self, s):
        p=subprocess.run(['pandoc','-f','latex+raw_tex','-t','json'],input=self.macros+'\n'+self.prep(s),text=True,capture_output=True)
        if p.returncode: raise RuntimeError(p.stderr)
        if p.stderr.strip(): raise ValueError('Pandoc warning: '+p.stderr)
        return json.loads(p.stdout)['blocks']

    def inlines(self, nodes):
        out=[]
        for n in nodes:
            t=n['t']; c=n.get('c')
            if t=='Str': out.append(ESC(c.replace('PTXENDANSWER','')))
            elif t in ('Space','SoftBreak','LineBreak'): out.append(' ')
            elif t in ('Strong','Emph','SmallCaps','Strikeout','Superscript','Subscript'):
                tag={'Strong':'alert','Emph':'em','SmallCaps':'em','Strikeout':'em','Superscript':'sup','Subscript':'sub'}[t]
                out.append(f'<{tag}>'+self.inlines(c)+f'</{tag}>')
            elif t=='Math':
                math=c[1]
                # Pandoc does not expand operators, so they live in docinfo/macros.
                math=re.sub(r'\\noalign\s*\{[^}]*\}', '', math)
                math=ESC(math)
                math=re.sub(r'\\text\{\[Blank (\d+)\]\}',lambda m:'<fillin characters="12"/>_{\\text{('+m[1]+')}}',math)
                if c[0]['t']=='DisplayMath': out.append('<me>'+math+'</me>')
                else: out.append('<m>'+math+'</m>')
            elif t=='Code':
                val=c[1]
                if val=='PTXENDANSWER': continue
                out.append(self.placeholders.get(val,'<c>'+ESC(val)+'</c>'))
            elif t=='RawInline':
                fmt,raw=c
                if fmt in ('tex','latex') and raw.startswith(r'\ref{'):
                    label=raw[5:-1]; out.append('<xref ref="'+ESC(label)+'" text="global"/>')
                elif fmt in ('tex','latex') and raw.startswith(r'\label{'): pass
                else: raise ValueError(f'Unhandled raw inline {c}')
            elif t=='Image':
                _,alt,(src,_)=c; src=Path(src).stem+'.png'
                original=ROOT/'Notes'/f'Chap{self.chapter}'/src
                if not original.exists(): raise FileNotFoundError(original)
                target=f'c{self.chapter}-{src}'; shutil.copy2(original,OUT/'assets/images'/target)
                STATS['images']+=1
                desc=self.inlines(alt) or Path(src).stem.replace('-',' ')
                out.append('</p><image source="images/'+target+'" width="70%"><shortdescription>'+desc+'</shortdescription></image><p>')
            elif t=='Span': out.append(self.inlines(c[1]))
            elif t=='Quoted': out.append('<q>'+self.inlines(c[1])+'</q>')
            elif t=='Link':
                attrs=dict(c[0][2])
                if attrs.get('reference-type')=='ref': out.append('<xref ref="'+ESC(attrs['reference'])+'" text="global"/>')
                else: out.append('<url href="'+ESC(c[2][0])+'">'+self.inlines(c[1])+'</url>')
            else: raise ValueError(f'Unhandled inline: {n}')
        return ''.join(out)

    def blocks(self, nodes):
        out=[]
        for n in nodes:
            t=n['t']; c=n.get('c')
            if t in ('Para','Plain'): out.append('<p>'+self.inlines(c)+'</p>')
            elif t in ('BulletList','OrderedList'):
                if t=='BulletList': tag='ul'; items=c; attr=''
                else:
                    tag='ol'; (start,style,delim),items=c
                    label={'LowerAlpha':'(a)','UpperAlpha':'A.','LowerRoman':'i.','UpperRoman':'I.'}.get(style['t'],'1.')
                    attr=' marker="'+label+'"'
                out.append('<p><'+tag+attr+'>'+''.join('<li>'+self.blocks(x)+'</li>' for x in items)+'</'+tag+'></p>')
            elif t=='Div': out.append(self.blocks(c[1]))
            elif t=='Figure':
                attr,caption,body=c
                out.append('<figure>'+('<caption>'+self.caption(caption)+'</caption>' if caption[1] else '<caption>Lecture illustration</caption>')+self.blocks(body)+'</figure>')
            elif t=='Header': out.append('<p><alert>'+self.inlines(c[2])+'</alert></p>')
            elif t=='RawBlock':
                if re.fullmatch(r'\\(?:quad|qquad)\s*',c[1]): continue
                raise ValueError(f'Unhandled raw block: {c}')
            elif t=='HorizontalRule': pass
            else: raise ValueError(f'Unhandled block: {n}')
        result=''.join(out)
        # Math and images are block-level PreTeXt; remove empty paragraph wrappers.
        result=re.sub(r'<p>\s*</p>','',result)
        return result

    def caption(self,c): return self.blocks(c[1]).removeprefix('<p>').removesuffix('</p>')

def macro_source(preamble):
    # Mathematical definitions stay in TeX and are re-read on every generation.
    start=preamble.index('%matrix entries')
    end=preamble.index('%%%%%%%%%%%%%%%%%%%%\n%%%DASH',start)
    base=strip_comments(preamble[start:end])
    # Correct an unused typo in the source macro for compatibility with MathJax.
    base=base.replace(r'\end{bmatrix}{r}',r'\end{array}')
    ops='\n'.join(re.findall(r'\\DeclareMathOperator\{[^}]+\}\{[^}]+\}',preamble))
    return base+'\n'+ops+r'\newcommand{\dashline}{\mathrel{\vert}}'+r'\newcommand{\bbR}{\mathbb{R}}'+r'\newcommand{\Ainv}{A^{-1}}'+r'\newcommand{\inv}{{^{-1}}}'+r'\newcommand{\ddd}{\mathrm{d}}'

def split_chunks(s):
    """Only top-level semantic markers split blocks; ignore commands in answers/math."""
    pattern=re.compile(r'\\(chaptertitle|sectiontitle|topic|'+ '|'.join(KINDS)+r')\b')
    depth=0; i=0; starts=[]
    while i<len(s):
        if s[i]=='\\':
            m=pattern.match(s,i)
            if m and depth==0: starts.append((i,m.end(),m[1])); i=m.end(); continue
            i+=2; continue
        if s[i]=='{': depth+=1
        elif s[i]=='}': depth-=1
        i+=1
    if depth: raise ValueError('Unbalanced source braces')
    if s[:starts[0][0]].strip(): raise ValueError('Unexpected text before chapter')
    return [(kind,s[end:starts[n+1][0] if n+1<len(starts) else len(s)]) for n,(_,end,kind) in enumerate(starts)]

def activity_scope(s):
    # End at the paragraph following the last answer. This keeps subsequent
    # exposition (and its filled-in vocabulary) outside the activity.
    # Unnumbered theorem/fact headings also end an activity. They do not
    # increment the source's shared counter.
    depth=0; i=0
    while i<len(s):
        if s[i]=='\\':
            if depth==0 and re.match(r'\\textit\{(?:Theorem|Fact):\}',s[i:]):
                scope,tail=activity_scope(s[:i]); return scope,tail+s[i:]
            i+=2; continue
        if s[i]=='{': depth+=1
        elif s[i]=='}': depth-=1
        i+=1
    spans=[]; skip=0
    for m in re.finditer(r'\\(?:answer|shortanswer|fillin|underline)\b',s):
        if m.start()<skip: continue
        j=m.end()
        while j<len(s) and s[j].isspace(): j+=1
        if s[j:j+1]=='[': _,j=group(s,j,'[',']')
        _,skip=group(s,j); spans.append((m[0],skip))
    if not spans: raise ValueError('Activity has no embedded solution')
    boxed=[end for kind,end in spans if kind==r'\answer']
    short=[end for kind,end in spans if kind==r'\shortanswer']
    last=boxed[-1] if boxed else short[-1] if short else spans[0][1]
    tail=s[last:]
    boundary=re.search(r'\n\s*\n',tail)
    split=last+boundary.end() if boundary else len(s)
    for env in ('enumerate','itemize'):
        if s[:split].count('\\begin{'+env+'}')>s[:split].count('\\end{'+env+'}'):
            k=s.find('\\end{'+env+'}',split)
            if k>=0: split=k+len('\\end{'+env+'}')
    return s[:split],s[split:]

def main():
    chapters=[]; mapping=[]; allmacros=None
    for p in sorted((ROOT/'Notes').glob('Chap*/*-lectures.tex')):
        raw=p.read_text(); preamble,body=raw.split(r'\begin{document}',1)
        body=strip_comments(body.split(r'\end{document}')[0])
        num=int(re.search(r'Chap(\d+)',str(p))[1]); macros=macro_source(preamble)
        allmacros=macros if allmacros is None else allmacros
        cv=Converter(num,macros); counter=0; chapter=[]; section=None; section_count=0
        for kind,s in split_chunks(body):
            if kind in ('chaptertitle','sectiontitle'):
                number,i=group(s,0); title,j=group(s,i); remainder=s[j:]
                if kind=='chaptertitle':
                    if int(number)!=num: raise ValueError('Chapter numbering mismatch')
                    chapter.append(f'<chapter xml:id="chapter-{num}"><title>{ESC(title.strip())}</title>')
                    text,_=cv.annotations(remainder)
                    chapter.append('<introduction>'+cv.blocks(cv.parse(text))+'</introduction>'); STATS['chapters']+=1
                else:
                    if section is not None: chapter.append('</section>')
                    section_count+=1
                    if number!=f'{num}.{section_count}': raise ValueError('Unexpected section numbering: '+number)
                    section=number
                    chapter.append(f'<section xml:id="section-{number.replace(".","-")}"><title>{ESC(title)}</title>')
                    text,_=cv.annotations(remainder); chapter.append(cv.blocks(cv.parse(text))); STATS['sections']+=1
            elif kind=='topic':
                title,j=group(s,0)
                chapter.append('<p><alert>'+cv.inlines(cv.parse(title)[0]['c'])+'</alert></p>')
                text,_=cv.annotations(s[j:]); chapter.append(cv.blocks(cv.parse(text)))
            else:
                counter+=1; tag={'fact':'axiom'}.get(kind,kind)
                labels=re.findall(r'^\s*\\label\{([^}]+)\}',s)
                ident=labels[0] if labels else f'c{num}-{kind}-n{counter}'
                s=re.sub(r'\\label\{[^}]+\}','',s)
                mapping.append({'chapter':num,'section':section,'kind':kind,'number':counter,'id':ident})
                if kind=='activity':
                    scope,tail=activity_scope(s); statement,answers=cv.annotations(scope,True)
                    blocks=cv.blocks(cv.parse(statement))
                    sol=[]
                    for label,answer in answers:
                        processed,_=cv.annotations(answer)
                        content=cv.blocks(cv.parse(processed))
                        if label.startswith('Blank'): content='<p><em>'+label+'.</em></p>'+content
                        sol.append(content)
                    chapter.append(f'<activity xml:id="{ident}"><statement>{blocks}</statement><solution>'+''.join(sol)+'</solution></activity>')
                    STATS['activities']+=1; STATS['solutions']+=1
                    text,_=cv.annotations(tail); chapter.append(cv.blocks(cv.parse(text)))
                else:
                    # A source TikZ figure immediately following a definition is a
                    # standalone figure, outside the definition's statement.
                    fig=re.search(r'\\begin\{figure\}',s) if r'\begin{tikzpicture}' in s else None
                    narrative=s[:fig.start()] if fig else s
                    trailing=s[fig.start():] if fig else ''
                    text,_=cv.annotations(narrative); content=cv.blocks(cv.parse(text))
                    if kind in ('theorem','corollary','lemma','fact','definition'): content='<statement>'+content+'</statement>'
                    chapter.append(f'<{tag} xml:id="{ident}">'+content+f'</{tag}>')
                    if trailing:
                        text,_=cv.annotations(trailing); chapter.append(cv.blocks(cv.parse(text)))
        chapter.append('</section></chapter>'); chapters.append(''.join(chapter))
    # Math macros are expanded by Pandoc; operators are retained for MathJax.
    docinfo='<docinfo><macros>'+ESC(allmacros)+'</macros><rename element="axiom">Fact</rename></docinfo>'
    xml='<?xml version="1.0" encoding="UTF-8"?>\n<!-- GENERATED from Notes/**/*.tex; edit the TeX, not this file. -->\n<pretext>'+docinfo+'<book xml:id="lecture-notes"><title>Math 345: Linear Algebra</title><subtitle>Lecture Notes</subtitle><frontmatter><bibinfo><author><personname>Sebastien Roch</personname></author></bibinfo><titlepage><titlepage-items/></titlepage></frontmatter>'+''.join(chapters)+'</book></pretext>'
    # Parse and pretty-print as a basic structural check.
    root=ET.fromstring(xml); ET.indent(root)
    (OUT/'source/main.ptx').write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!-- GENERATED: edit Notes/**/*.tex instead. -->\n'+ET.tostring(root,encoding='unicode'))
    (OUT/'source-map.json').write_text(json.dumps(mapping,indent=2)+'\n')
    # Override only block numbers: the original TeX uses a chapter-wide shared
    # counter for activities, definitions, theorems, notes, and facts.
    templates=[]
    for item in mapping:
        ident=item['id']; number=item['number']
        templates.append(f'<xsl:template match="*[@xml:id=\'{ident}\']" mode="number"><xsl:text>{number}</xsl:text></xsl:template>')
    (OUT/'xsl/lecture-html.xsl').write_text('<?xml version="1.0"?>\n<xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform"><xsl:import href="core/pretext-html.xsl"/>'+''.join(templates)+'</xsl:stylesheet>')
    (OUT/'conversion-report.json').write_text(json.dumps(STATS,indent=2)+'\n')
    print(json.dumps(STATS,indent=2))

if __name__=='__main__': main()
