"""Passive BioNexus intake and bounded rule evaluation for completed artifacts."""
from pathlib import Path
import json,sys,hashlib,subprocess,shutil
from datetime import datetime,timezone
from dataclasses import asdict
rec=Path(__file__).resolve().parent; root=rec.parents[2]; out=rec.with_name('workbench-run-01'); aud=rec/'audit'; aud.mkdir(exist_ok=False)
sys.path.insert(0,str(root/'src'))
from bionexus.ecosystem_intake import ExternalEvidenceEnvelope,ExternalProducerIdentity
from bionexus.claim_semantics import DeterministicClaimParser,DeterministicWarrantEngine,EvidenceProfile
def save(p,x): p.write_text(json.dumps(x,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
m=read(out/'analysis_manifest.json'); verification=read(rec/'verification.json'); commands=read(rec/'commands.json')
save(aud/'analysis-parameters.json',{'method':m['method'],'cell_policy':m['qc']['policy'],'prespecified_genes':['ISG15','IFIT1','MX1','STAT1'],'refit_cooks':True,'independent_filter':True,'alpha':0.05,'n_cpus':1})
envelopes=[ExternalEvidenceEnvelope.create(evidence_id='IFNB-RUN01-ANALYSIS',family='analysis',producer=ExternalProducerIdentity(plugin_id='local-python-demo-not-ngs-workflow',capability='paired_pseudobulk_de',tool_name='review/workbench-ifnb-demo/run_analysis.py',plugin_version=m['script_sha256']),payload=m,request=commands[-1]['argv'],source_context={'backend_name':'PyDESeq2','backend_version':m['runtime']['pydeseq2'],'input_artifact_sha256':sha(rec/'input-sha256.json'),'input_hash_semantics':'SHA-256 of the manifest binding all three actual input file hashes','parameters_sha256':sha(aud/'analysis-parameters.json'),'execution_receipt_sha256':sha(rec/'commands.json'),'geo_accession':'GSE96583','donors':8,'condition_library_confounded':True,'independent_validation':False}),ExternalEvidenceEnvelope.create(evidence_id='IFNB-RUN01-PUBMED',family='literature',producer=ExternalProducerIdentity(plugin_id='life-sciences-literature',capability='pubmed_article_fetch',tool_name='ncbi-entrez-skill/scripts/ncbi_entrez.py',plugin_version='0.1.5'),payload=read(rec/'literature/pubmed-article.response.json'),request=read(rec/'literature/pubmed-article.request.json'),source_context={'source_name':'PubMed','identifiers':['PMID:29227470','DOI:10.1038/nbt.4042','PMCID:PMC5784859'],'publication_status':'published journal article; linked 2020 author correction exists','study_design':'8 lupus donors, paired 6-hour IFN-beta/control aliquots pooled separately by condition','same_primary_study_as_analysis':True,'independent_validation':False})]
audit_commands=[]
for env in envelopes:
    p=aud/(env.evidence_id+'.envelope.json'); save(p,env.to_dict()); result=aud/(env.evidence_id+'.audit.json')
    argv=[sys.executable,str(root/'skills/external-evidence-audit/scripts/audit_external_evidence.py'),str(p),'--out',str(result)]; started=datetime.now(timezone.utc).isoformat(); proc=subprocess.run(argv,cwd=root,capture_output=True)
    (aud/(env.evidence_id+'.stdout.log')).write_bytes(proc.stdout); (aud/(env.evidence_id+'.stderr.log')).write_bytes(proc.stderr); audit_commands.append({'argv':argv,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),'exit_code':proc.returncode})
    print(env.evidence_id,'exit',proc.returncode); print(json.dumps(read(result),ensure_ascii=True))
save(aud/'commands.json',audit_commands)
statement='Within the GSE96583 cohort, the IFN-beta condition is associated with donor-paired expression differences in source-annotated CD14+ Monocytes.'
claim=DeterministicClaimParser.parse(statement,claim_id='IFNB-RUN01-COHORT-ASSOCIATION')
evidence=EvidenceProfile(observational_data=True,biological_replicates_count=8,pseudobulk_aggregated=True,confound_controls=['donor'],causal_identification_status='UNBLOCKED_BACKDOOR',independent_validation=False,reference_ground_truth=False,cross_method_concordance=False)
save(aud/'claim-review-input.json',{'statement':statement,'claim_ir':claim.to_dict(),'evidence_profile':evidence.to_dict(),'basis':{'analysis_manifest_sha256':sha(out/'analysis_manifest.json'),'verification_sha256':sha(rec/'verification.json')},'evidence_assignment':'Codex supplied facts from this completed run; not an independent human adjudication','mandatory_qualifications':['Condition and sequencing library are fully confounded; IFN-beta-specific causal effect is not identified.','Source labels are not independently validated.','No external replication or human scientific acceptance.'],'human_scientific_decision':'PENDING'})
review=DeterministicWarrantEngine.evaluate(claim,evidence); save(aud/'claim-review-result.json',review.to_dict()); print('CLAIM_REVIEW',json.dumps(review.to_dict(),ensure_ascii=True))
save(aud/'identity-audit-extracted.json',m['bionexus_identity_audit'])
pre=root/'review/workbench-ifnb-demo/preflight-2026-09-04'
for name in ['bionexus_warrant_initial.json','bionexus_warrant_verified_inputs.json','ngs_catalog.json','ngs_compute_targets.json','analysis_plan.md','starting_point_assessment.md']:
    shutil.copy2(pre/name,aud/('preflight-'+name))
save(aud/'audit-code-sha256.json',{str(p.relative_to(root)):sha(p) for p in [Path(__file__),root/'skills/external-evidence-audit/scripts/audit_external_evidence.py',root/'src/bionexus/ecosystem_intake.py',root/'src/bionexus/claim_semantics.py',root/'src/bionexus/annotation_evidence.py']})
