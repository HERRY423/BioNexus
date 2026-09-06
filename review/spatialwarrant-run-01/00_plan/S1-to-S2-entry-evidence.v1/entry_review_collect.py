import pathlib, json, hashlib, datetime, shutil, subprocess, sys, gzip, csv, collections, xml.etree.ElementTree as ET
R=pathlib.Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01')
E=R/'00_plan/S1-to-S2-entry-evidence.v1'
def now(): return datetime.datetime.now(datetime.timezone.utc).isoformat()
def h(p):
    d=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''): d.update(b)
    return d.hexdigest()
def put(name,obj):
    if shutil.disk_usage('C:\\').free<20*1024**3: raise RuntimeError('STORAGE_FLOOR')
    with (E/name).open('x',encoding='utf-8',newline='\n') as f: json.dump(obj,f,indent=2,ensure_ascii=True);f.write('\n')
assert h(R/'00_plan/analysis-plan.lock.md')=='854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82'
assert shutil.disk_usage('C:\\').free>=30*1024**3
E.mkdir(exist_ok=False)
put('storage.v1.json',{'observed_at_utc':now(),'free_C_bytes':shutil.disk_usage('C:\\').free,'start_min_bytes':30*1024**3,'stop_write_below_bytes':20*1024**3,'S2_started':False})
checks=[]
for line in (R/'manifest/S1-artifact-index.sha256').read_text(encoding='utf-8').splitlines():
    expected,rel=line.split('  ',1);p=R/rel
    actual=h(p) if p.is_file() else None
    checks.append({'file':rel,'expected_sha256':expected,'actual_sha256':actual,'match':actual==expected,'bytes':p.stat().st_size if p.exists() else None})
put('S1-artifact-verification.v1.json',{'created':now(),'method':'Exact-byte streaming SHA-256 only; no matrix count entries parsed or analyzed','files':checks,'all_match':all(c['match'] for c in checks)})
idx=json.loads((R/'manifest/S1-input-file-index.json').read_text(encoding='utf-8'))
lookup={c['file'].replace('\\','/'):c for c in checks}
cross=[]
for x in idx['files']:
    rel=x['relative_path'].replace('\\','/');c=lookup.get(rel)
    cross.append({'file':rel,'match':bool(c and c['match'] and c['actual_sha256']==x['sha256_raw_bytes'] and c['bytes']==x['bytes'])})
put('input-index-crosscheck.v1.json',{'files':cross,'all_match':all(x['match'] for x in cross)})
softp=R/'01_inputs/source_metadata/GSE176078_family.soft.gz'
soft=gzip.decompress(softp.read_bytes()).decode('utf-8')
samples=[]
for block in soft.split('^SAMPLE = ')[1:]:
    lines=block.splitlines();fields=collections.defaultdict(list)
    for line in lines[1:]:
        if line.startswith('!Sample_') and ' = ' in line:
            k,v=line.split(' = ',1);fields[k].append(v)
    samples.append({'geo_accession':lines[0],'fields':dict(fields)})
meta=next((R/'01_inputs/GSE176078').glob('*-extracted/*/metadata.csv'))
with meta.open(encoding='utf-8-sig',newline='') as f:
    dr=csv.DictReader(f);cols=dr.fieldnames;rows=list(dr)
counts=collections.Counter(row['orig.ident'] for row in rows)
bc=next((R/'01_inputs/GSE176078').glob('*-extracted/*/count_matrix_barcodes.tsv')).read_text(encoding='utf-8').splitlines()
ident={'created':now(),'metadata_file':str(meta),'metadata_sha256':h(meta),'metadata_columns':cols,'source_sample_counts':dict(sorted(counts.items())),'barcode_unique':len(bc)==len(set(bc)),'barcode_order_equals_metadata':bc==[x[''] for x in rows],'missing_orig_ident':sum(not x['orig.ident'].strip() for x in rows),'missing_minor_label':sum(not x['celltype_minor'].strip() for x in rows),'minor_label_values':sorted(set(x['celltype_minor'] for x in rows)),'GEO_source_file':str(softp),'GEO_source_sha256':h(softp),'GEO_samples':samples,'metadata_orig_ident_equals_GEO_sample_titles':set(counts)=={x['fields']['!Sample_title'][0] for x in samples},'scope':'Metadata identifier/label inspection only; source nCount_RNA/nFeature_RNA/percent.mito values not used or summarized; no expression matrix parsed.'}
put('GEO-metadata-identity-evidence.v1.json',ident)
pmcp=R/'01_inputs/literature/PMC9044823-BioC.xml';tree=ET.fromstring(pmcp.read_bytes());ex=[]
for p in tree.findall('.//passage'):
    t=p.findtext('text') or ''
    if any(q.lower() in t.lower() for q in ['CID4290','orig.ident','26 primary','three tissue regions','sample collection','single-cell rna sequencing']):
        ex.append({'offset':p.findtext('offset'),'section':{i.attrib.get('key'):i.text for i in p.findall('infon')},'text':t})
put('PMC-existing-identity-passages.v1.json',{'source_file':str(pmcp),'source_sha256':h(pmcp),'passages':ex,'query_terms':['CID4290','orig.ident','26 primary','three tissue regions','sample collection','single-cell rna sequencing'],'CID4290A_literal_occurrences':pmcp.read_text(encoding='utf-8').count('CID4290A'),'note':'Source passages for provenance only; no findings accepted; no literature used to define primary boundary.'})
script=pathlib.Path(r'C:\Users\13264\.codex\plugins\cache\openai-curated-remote\life-sciences-literature\0.1.5\skills\ncbi-pmc-skill\scripts\ncbi_pmc.py')
req={'params':{'id':'PMC9044823'},'max_items':20,'timeout_sec':30,'save_raw':True,'raw_output_path':str(E/'PMC-plugin-raw.v1.json')}
put('PMC-plugin-request.v1.json',req);started=now()
try:
    c=subprocess.run([sys.executable,'-B',str(script)],input=json.dumps(req).encode(),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=55)
    (E/'PMC-plugin-stdout.v1.json').write_bytes(c.stdout);(E/'PMC-plugin-stderr.v1.txt').write_bytes(c.stderr)
    put('PMC-plugin-call.v1.json',{'started':started,'finished':now(),'script':str(script),'script_sha256':h(script),'returncode':c.returncode,'request_file':'PMC-plugin-request.v1.json','stdout_file':'PMC-plugin-stdout.v1.json','stderr_file':'PMC-plugin-stderr.v1.txt','plugin':'Life Sciences Literature 0.1.5','execution':'Actual skill-local Python script; no dedicated MCP claim'})
    print(c.stdout.decode('utf-8',errors='replace'))
except Exception as e: put('PMC-plugin-failure.v1.json',{'started':started,'finished':now(),'type':type(e).__name__,'error':str(e)})
print(json.dumps({'artifact_count':len(checks),'all_artifacts_match':all(c['match'] for c in checks),'indexed_inputs':len(cross),'all_inputs_match':all(x['match'] for x in cross),'source_sample_count':len(counts),'orig_ident_equals_GEO_titles':ident['metadata_orig_ident_equals_GEO_sample_titles'],'evidence_dir':str(E)}))
