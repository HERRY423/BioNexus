import hashlib, json, sys
from datetime import datetime, timezone
from pathlib import Path

root=Path(sys.argv[1])
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''): h.update(b)
 return h.hexdigest()
for d in [root/'08_pseudobulk'/'S6-run-01',root/'09_liana_literature'/'S6-run-01']:
 files=[]
 for p in sorted(d.rglob('*'),key=lambda x:str(x).lower()):
  if p.is_file() and p.name not in {'output-manifest.json','SHA256SUMS.txt'} and not p.name.endswith('.tmp'):
   files.append({'path':p.relative_to(d).as_posix(),'bytes':p.stat().st_size,'sha256':sha(p)})
 (d/'output-manifest.json').write_text(json.dumps({'created_at_utc':datetime.now(timezone.utc).isoformat(),'root':str(d),'files':files,'total_bytes_excluding_manifest':sum(x['bytes'] for x in files)},indent=2)+'\n',encoding='utf-8')
 lines=[]
 for p in sorted(d.rglob('*'),key=lambda x:str(x).lower()):
  if p.is_file() and p.name!='SHA256SUMS.txt' and not p.name.endswith('.tmp'): lines.append(f'{sha(p)}  {p.relative_to(d).as_posix()}')
 (d/'SHA256SUMS.txt').write_text('\n'.join(lines)+'\n',encoding='utf-8')
