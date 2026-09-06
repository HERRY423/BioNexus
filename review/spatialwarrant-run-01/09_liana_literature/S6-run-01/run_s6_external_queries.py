from __future__ import annotations

import concurrent.futures
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


DB_SKILLS = Path(r"C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-databases\0.1.5\skills")
LIT_SKILLS = Path(r"C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-literature\0.1.5\skills")
REST = DB_SKILLS / "reactome-skill" / "scripts" / "rest_request.py"
OT = DB_SKILLS / "opentargets-skill" / "scripts" / "opentargets_graphql.py"
PUBMED = LIT_SKILLS / "ncbi-entrez-skill" / "scripts" / "ncbi_entrez.py"
PYTHON = Path(r"C:\Users\13264\anaconda3\python.exe")


def utcnow():
    return datetime.now(timezone.utc).isoformat()


def slug(x):
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(x)).strip("_")
    return s[:120] or "query"


def genes_from_term(term):
    stop = {"CANCER","INTERACTION","FAMILY","HALLMARK","INTERFERON","GAMMA","RESPONSE","BREAST"}
    vals = []
    for x in re.findall(r"[A-Z][A-Z0-9-]{1,20}", term.upper()):
        if x not in stop and x not in vals:
            vals.append(x)
    return vals[:8]


def request_specs(target):
    name = target["name"]
    genes = genes_from_term(name)
    gene_query = genes[0] if target["kind"] == "gene" and genes else name
    uni_q = " OR ".join(f"gene:{g}" for g in genes) if genes else name
    ids = "\r".join(genes) if genes else name
    reactome = {"base_url":"https://reactome.org/ContentService","path":"search/query","params":{"query":name,"species":"Homo sapiens"},
                "headers":{"Accept":"application/json"},"max_items":10,"save_raw":True}
    string = {"base_url":"https://string-db.org/api/json","path":"network","method":"POST",
              "form_body":{"identifiers":ids,"species":9606,"caller_identity":"spatialwarrant-s6","limit":10},"max_items":10,"save_raw":True}
    ot_query = "query searchAny($q: String!) { search(queryString: $q) { total hits { entity score object { ... on Target { id approvedSymbol approvedName } ... on Disease { id name } ... on Drug { id name } } } } }"
    opentargets = {"query":ot_query,"variables":{"q":name},"max_items":10,"save_raw":True}
    uniprot = {"base_url":"https://rest.uniprot.org","path":"uniprotkb/search","params":{"query":f"({uni_q}) AND organism_id:9606","fields":"accession,id,gene_names,protein_name,cc_function","size":10,"format":"json"},
               "record_path":"results","max_items":10,"save_raw":True}
    pm_term = f'({name}) AND (breast cancer OR tumor microenvironment) AND (journal article[pt] NOT review[pt])'
    pubmed = {"endpoint":"esearch","params":{"db":"pubmed","term":pm_term,"retmode":"json","retmax":10,"sort":"relevance"},"max_items":10,"save_raw":True}
    return {"reactome":(REST,reactome),"string":(REST,string),"opentargets":(OT,opentargets),"uniprot":(REST,uniprot),"pubmed":(PUBMED,pubmed)}


def run_one(base, target, source, script, payload):
    key = f"{target['kind']}-{target['rank']:02d}-{slug(target['name'])}"
    req_dir, raw_dir, resp_dir = base/"requests"/source, base/"raw"/source, base/"responses"/source
    req_dir.mkdir(parents=True, exist_ok=True); raw_dir.mkdir(parents=True, exist_ok=True); resp_dir.mkdir(parents=True, exist_ok=True)
    req_path, raw_path, resp_path = req_dir/f"{key}.request.json", raw_dir/f"{key}.raw", resp_dir/f"{key}.wrapper.json"
    payload = dict(payload); payload["raw_output_path"] = str(raw_path)
    req_record = {"target":target,"source":source,"script":str(script),"requested_at_utc":utcnow(),"payload":payload}
    req_path.write_text(json.dumps(req_record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    t0=time.perf_counter()
    try:
        p=subprocess.run([str(PYTHON),str(script)],input=json.dumps(payload),text=True,capture_output=True,timeout=90)
        out=p.stdout.strip()
        try: wrapper=json.loads(out) if out else {"ok":False,"error":{"code":"empty_stdout","message":"no wrapper output"}}
        except Exception: wrapper={"ok":False,"error":{"code":"invalid_wrapper_json","message":out[:2000]},"stderr":p.stderr[-2000:]}
        wrapper_record={"target":target,"source":source,"returncode":p.returncode,"elapsed_seconds":time.perf_counter()-t0,
                        "completed_at_utc":utcnow(),"request_path":str(req_path),"raw_output_path":str(raw_path),"wrapper":wrapper,"stderr":p.stderr[-4000:]}
    except Exception as e:
        wrapper_record={"target":target,"source":source,"returncode":None,"elapsed_seconds":time.perf_counter()-t0,"completed_at_utc":utcnow(),
                        "request_path":str(req_path),"raw_output_path":str(raw_path),"wrapper":{"ok":False,"error":{"code":"runner_exception","message":repr(e)}}}
    resp_path.write_text(json.dumps(wrapper_record,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    w=wrapper_record["wrapper"]
    return {"kind":target["kind"],"rank":target["rank"],"target":target["name"],"source":source,"ok":bool(w.get("ok",False)),
            "status_code":w.get("status_code"),"error_code":(w.get("error") or {}).get("code"),"request_path":str(req_path),
            "response_path":str(resp_path),"raw_path":str(raw_path),"raw_exists":raw_path.exists(),"elapsed_seconds":wrapper_record["elapsed_seconds"],
            "source_url": {"reactome":"https://reactome.org/ContentService","string":"https://string-db.org","opentargets":"https://platform.opentargets.org","uniprot":"https://rest.uniprot.org","pubmed":"https://pubmed.ncbi.nlm.nih.gov"}[source]}


def main():
    root=Path(sys.argv[1])
    out=root/"09_liana_literature"/"S6-run-01"
    targets=json.loads((out/"external-evidence-query-targets.json").read_text(encoding="utf-8"))
    entries=[]
    for x in targets["top20_genes"]:
        entries.append({"kind":"gene","rank":int(x["deterministic_rank"]),"name":str(x["gene_id"])})
    for x in targets["top10_liana_interactions"]:
        entries.append({"kind":"liana_interaction","rank":int(x["rank"]),"name":f"{x['ligand']} {x['receptor']}"})
    for i,x in enumerate(targets["prespecified_items"],1):
        entries.append({"kind":"prespecified","rank":i,"name":x})
    jobs=[]
    for t in entries:
        for source,(script,payload) in request_specs(t).items():
            jobs.append((t,source,script,payload))
    started=utcnow(); t0=time.perf_counter()
    rows=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs=[ex.submit(run_one,out,t,s,sc,p) for t,s,sc,p in jobs]
        for i,f in enumerate(concurrent.futures.as_completed(futs),1):
            rows.append(f.result())
            if i%10==0:
                tmp={"status":"RUNNING","stage":"external_queries","completed":i,"total":len(jobs),"percent":85+10*i/len(jobs),"updated_at_utc":utcnow()}
                (out/"progress.json.tmp").write_text(json.dumps(tmp,indent=2)+"\n",encoding="utf-8"); os.replace(out/"progress.json.tmp",out/"progress.json")
    df=pd.DataFrame(rows).sort_values(["kind","rank","target","source"])
    df.to_csv(out/"external-query-log.csv",index=False)
    summary={"status":"COMPLETED_WITH_PRESERVED_FAILURES" if not df.ok.all() else "COMPLETED","started_at_utc":started,"ended_at_utc":utcnow(),
             "elapsed_seconds":time.perf_counter()-t0,"requests":len(df),"successes":int(df.ok.sum()),"failures":int((~df.ok).sum()),
             "sources":df.groupby("source")["ok"].agg(["count","sum"]).reset_index().to_dict("records"),
             "selection_rule":targets["selection_rule"],"raw_return_policy":"Every request, wrapper return, raw payload path, timestamp, source URL, and failure retained.",
             "evidence_adjudication":"UNASSESSED: returned database/literature context is not automatically labeled support or contradiction.",
             "contradictory_evidence":"NOT_HUMAN_ADJUDICATED",
             "not_verifiable_from_current_data":["causal direction","patient-level consistency","clinical prediction","independent cohort replication","cell-type-resolved boundary sender/receiver expression"]}
    (out/"external-evidence-summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    evidence=[]
    for t in entries:
        sub=df[(df.kind==t["kind"])&(df["rank"]==t["rank"])&(df.target==t["name"])]
        evidence.append({"kind":t["kind"],"rank":t["rank"],"target":t["name"],"successful_sources":";".join(sub.loc[sub.ok,"source"]),
                         "failed_sources":";".join(sub.loc[~sub.ok,"source"]),"support_evidence":"CANDIDATE_CONTEXT_NOT_ADJUDICATED",
                         "contradictory_evidence":"NOT_HUMAN_ADJUDICATED","current_data_can_verify":"descriptive CID4535 molecular difference or scRNA communication score only",
                         "current_data_cannot_verify":"causality, population effect, clinical relevance, independent replication"})
    pd.DataFrame(evidence).to_csv(out/"external-evidence-adjudication-register.csv",index=False)
    prog={"status":"EXTERNAL_QUERIES_COMPLETED","stage":"external_queries_complete","percent":95,"completed":len(jobs),"total":len(jobs),"updated_at_utc":utcnow()}
    (out/"progress.json.tmp").write_text(json.dumps(prog,indent=2)+"\n",encoding="utf-8"); os.replace(out/"progress.json.tmp",out/"progress.json")
    print(json.dumps(summary))


if __name__=="__main__":
    main()
