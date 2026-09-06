from __future__ import annotations
import concurrent.futures, importlib.util, json, sys, time
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd

ROOT=Path(sys.argv[1]); OUT=ROOT/'09_liana_literature'/'S6-run-01'; BASE=OUT/'raw-source-v2'
DB=Path(r'C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-databases\0.1.5\skills')
LIT=Path(r'C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-literature\0.1.5\skills')
scripts={'reactome':DB/'reactome-skill'/'scripts'/'rest_request.py','string':DB/'string-skill'/'scripts'/'rest_request.py','opentargets':DB/'opentargets-skill'/'scripts'/'opentargets_graphql.py','uniprot':DB/'uniprot-skill'/'scripts'/'rest_request.py','pubmed':LIT/'ncbi-entrez-skill'/'scripts'/'ncbi_entrez.py'}
spec=importlib.util.spec_from_file_location('qmod',OUT/'run_s6_external_queries.py'); qmod=importlib.util.module_from_spec(spec); spec.loader.exec_module(qmod)
q=json.loads((OUT/'external-evidence-query-targets.raw-source-v2.json').read_text(encoding='utf-8'))
entries=[{'kind':'gene','rank':int(x['deterministic_rank']),'name':str(x['gene_id'])} for x in q['top20_genes']]
jobs=[]
for t in entries:
 for source,(_,payload) in qmod.request_specs(t).items(): jobs.append((t,source,scripts[source],payload))
t0=time.perf_counter(); rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
 for f in concurrent.futures.as_completed([ex.submit(qmod.run_one,BASE,*j) for j in jobs]): rows.append(f.result())
r=pd.DataFrame(rows).sort_values(['kind','rank','target','source']); r['attempt']='raw-source-v2'; r.to_csv(OUT/'external-query-log.raw-source-v2.csv',index=False)
old=pd.read_csv(OUT/'external-query-log.consolidated.csv'); old=old[old.kind!='gene'].copy(); final=pd.concat([r,old],ignore_index=True).sort_values(['kind','rank','target','source']); final.to_csv(OUT/'external-query-log.final.csv',index=False)
summary={'status':'COMPLETED_WITH_PRESERVED_FAILURES' if not final.ok.all() else 'COMPLETED','correction':'Final gene target set derives from publisher raw_feature_bc_matrix. Earlier filtered-matrix query returns remain preserved but are not the final top20 set.',
 'raw_top20_requests':len(r),'raw_top20_successes':int(r.ok.sum()),'raw_top20_failures':int((~r.ok).sum()),'final_requests':len(final),'final_successes':int(final.ok.sum()),'final_failures':int((~final.ok).sum()),'sources':final.groupby('source')['ok'].agg(['count','sum']).reset_index().to_dict('records'),'elapsed_seconds':time.perf_counter()-t0,'completed_at_utc':datetime.now(timezone.utc).isoformat(),'evidence_adjudication':'UNASSESSED; no automatic support or contradiction label'}
(OUT/'external-evidence-summary.final.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf-8'); print(json.dumps(summary))
