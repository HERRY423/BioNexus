from __future__ import annotations
import concurrent.futures, importlib.util, json, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(sys.argv[1]); OUT=ROOT/'09_liana_literature'/'S6-run-01'; RETRY=OUT/'retry1'
PY=Path(r'C:\Users\13264\anaconda3\python.exe')
DB=Path(r'C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-databases\0.1.5\skills')
STRING=DB/'string-skill'/'scripts'/'rest_request.py'
UNIPROT=DB/'uniprot-skill'/'scripts'/'rest_request.py'
spec=importlib.util.spec_from_file_location('qmod',OUT/'run_s6_external_queries.py'); qmod=importlib.util.module_from_spec(spec); spec.loader.exec_module(qmod)

def entries():
    q=json.loads((OUT/'external-evidence-query-targets.json').read_text(encoding='utf-8'))
    z=[]
    for x in q['top20_genes']: z.append({'kind':'gene','rank':int(x['deterministic_rank']),'name':str(x['gene_id'])})
    for x in q['top10_liana_interactions']: z.append({'kind':'liana_interaction','rank':int(x['rank']),'name':f"{x['ligand']} {x['receptor']}"})
    for i,x in enumerate(q['prespecified_items'],1): z.append({'kind':'prespecified','rank':i,'name':x})
    return z

jobs=[]
for t in entries():
    s=qmod.request_specs(t)
    jobs.append((t,'string',STRING,s['string'][1]))
    jobs.append((t,'uniprot',UNIPROT,s['uniprot'][1]))
t0=time.perf_counter(); rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    fs=[ex.submit(qmod.run_one,RETRY,*j) for j in jobs]
    for f in concurrent.futures.as_completed(fs): rows.append(f.result())
r=pd.DataFrame(rows).sort_values(['kind','rank','target','source']); r.to_csv(OUT/'external-query-log.retry1.csv',index=False)
base=pd.read_csv(OUT/'external-query-log.csv')
combined=base[~base.source.isin(['string','uniprot'])].copy()
r['attempt']='retry1_correct_skill_wrapper'; combined['attempt']='initial'
combined=pd.concat([combined,r],ignore_index=True).sort_values(['kind','rank','target','source'])
combined.to_csv(OUT/'external-query-log.consolidated.csv',index=False)
summary={'status':'COMPLETED_WITH_PRESERVED_FAILURES' if not combined.ok.all() else 'COMPLETED','repair_reason':'Initial STRING and UniProt calls used the Reactome skill wrapper and were rejected as invalid_input; initial records retained, retry1 uses each source-specific skill wrapper.',
         'retry_requests':len(r),'retry_successes':int(r.ok.sum()),'retry_failures':int((~r.ok).sum()),'consolidated_requests':len(combined),'consolidated_successes':int(combined.ok.sum()),'consolidated_failures':int((~combined.ok).sum()),
         'sources':combined.groupby('source')['ok'].agg(['count','sum']).reset_index().to_dict('records'),'elapsed_seconds':time.perf_counter()-t0,'completed_at_utc':datetime.now(timezone.utc).isoformat()}
(OUT/'external-evidence-summary.v2.json').write_text(json.dumps(summary,indent=2)+"\n",encoding='utf-8')
print(json.dumps(summary))
