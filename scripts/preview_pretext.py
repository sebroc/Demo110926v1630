#!/usr/bin/env python3
"""Build, serve, and automatically regenerate the notes when source files change."""
from pathlib import Path
import argparse, functools, hashlib, http.server, json, shutil, subprocess, sys, threading, time
ROOT=Path(__file__).resolve().parents[1]
PROJECT=ROOT/'PreTeXt'
STATE={'version':0,'building':False,'error':None}

def fingerprint():
    paths=list((ROOT/'Notes').rglob('*.tex'))+list((ROOT/'Notes').rglob('*.png'))
    paths += [ROOT/'scripts/generate_pretext.py',PROJECT/'project.ptx',PROJECT/'publication/publication.ptx']
    digest=hashlib.sha256()
    for p in sorted(paths): digest.update(str(p).encode());digest.update(p.read_bytes())
    return digest.hexdigest()

def build():
    STATE['building']=True;STATE['error']=None
    try:
        cli=shutil.which('pretext')
        if not cli or not shutil.which('pandoc'): raise RuntimeError('Install pretext and pandoc; see PreTeXt/README.md')
        logfile=PROJECT/'build.log'
        with logfile.open('w') as log:
            subprocess.run([sys.executable,str(ROOT/'scripts/generate_pretext.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
            subprocess.run([cli,'build','web','--no-generate'],cwd=PROJECT,stdout=log,stderr=subprocess.STDOUT,check=True)
            subprocess.run([sys.executable,str(ROOT/'scripts/verify_pretext.py')],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True)
        STATE['version']+=1;STATE['error']=None
        print(f'Built successfully (revision {STATE["version"]}).',flush=True)
        return True
    except Exception as exc:
        STATE['error']=str(exc)
        print(f'Build failed: {exc}. See {PROJECT/"build.log"}',flush=True)
        return False
    finally: STATE['building']=False

LIVE_RELOAD='''<script>
(async()=>{let initial=null;setInterval(async()=>{try{const s=await(await fetch('/__preview_status',{cache:'no-store'})).json();if(initial===null)initial=s.version;else if(s.version!==initial)location.reload();}catch(e){}},1500);})();
</script>'''
class Handler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.split('?')[0]=='/__preview_status':
            payload=json.dumps(STATE).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(payload);return
        path=Path(self.translate_path(self.path))
        if path.is_dir(): path=path/'index.html'
        if path.suffix=='.html' and path.is_file():
            data=path.read_text().replace('</body>',LIVE_RELOAD+'</body>').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.end_headers();self.wfile.write(data);return
        super().do_GET()
    def log_message(self,*args): pass

def watch():
    last=fingerprint()
    while True:
        time.sleep(1)
        current=fingerprint()
        if current!=last:
            time.sleep(.5) # allow an editor's atomic save to settle
            last=fingerprint();print('TeX/assets changed; rebuilding...',flush=True);build()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--build-only',action='store_true')
    parser.add_argument('--skip-build',action='store_true')
    args=parser.parse_args()
    if not args.skip_build and not build(): return 1
    if args.build_only: return 0
    if not (PROJECT/'output/web/index.html').exists(): raise RuntimeError('Build the site first')
    handler=functools.partial(Handler,directory=str(PROJECT/'output/web'))
    server=http.server.ThreadingHTTPServer(('127.0.0.1',args.port),handler)
    threading.Thread(target=watch,daemon=True).start()
    print(f'Local preview: http://127.0.0.1:{args.port}/ — watching Notes/**/*.tex and figures. Ctrl+C to stop.',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
    return 0
if __name__=='__main__': sys.exit(main())
