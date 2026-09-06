import pathlib,json,hashlib,datetime,shutil,csv,collections
R=pathlib.Path(r'C:\Plugin\BioNexus\review\spatialwarrant-run-01')
E=R/'00_plan/S1-to-S2-entry-evidence.v1'
PLAN='854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82'
def sha(p):
 d=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(4*1024**2),b''):d.update(b)
 return d.hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def put(rel,obj):
 assert shutil.disk_usage('C:\\').free>=20*1024**3,'STOP_WRITING_STORAGE_FLOOR'
 with (R/rel).open('x',encoding='utf-8',newline='\n') as f:
  f.write(obj if isinstance(obj,str) else json.dumps(obj,ensure_ascii=False,indent=2)+'\n')
def stamp():return datetime.datetime.now(datetime.timezone.utc).isoformat()
assert sha(R/'00_plan/analysis-plan.lock.md')==PLAN
verify=read(E/'S1-artifact-verification.v1.json');assert verify['all_match']
assert read(E/'input-index-crosscheck.v1.json')['all_match']
identity=read(E/'GEO-metadata-identity-evidence.v1.json')
assert identity['metadata_orig_ident_equals_GEO_sample_titles'] and identity['barcode_order_equals_metadata']
required=['00_plan/analysis-plan.lock.md','S1-checkpoint.md','S1-starting-point-assessment.json','02_identity/identity-gate.json','02_identity/sample-identity.csv','02_identity/visium-sample-identity.csv','02_identity/pathology-label-map.json','02_identity/pathology-label-inventory.csv','02_identity/primary-program.lock.json','manifest/S1-source-manifest.json','manifest/S1-input-file-index.json']
required_records=[]
for rel in required:
 p=R/rel;b=p.read_bytes();txt=b.decode('utf-8-sig')
 if p.suffix=='.json':json.loads(txt)
 elif p.suffix=='.csv':list(csv.DictReader(txt.splitlines()))
 required_records.append({'file':rel,'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest(),'read_in_full':True,'matches_S1_manifest':any(x['file'].replace('\\','/')==rel and x['actual_sha256']==hashlib.sha256(b).hexdigest() and x['match'] for x in verify['files'])})
assert all(x['matches_S1_manifest'] for x in required_records)
geo={s['fields']['!Sample_title'][0]:s for s in identity['GEO_samples']}
resolution={
 'artifact_type':'scRNA_identity_resolution','version':'1','created_at_utc':stamp(),'approved_parent_plan_sha256':PLAN,
 'decision_scope':'Read-only identity evidence adjudication; not a biological verdict, not S2 execution authorization',
 'canonical_technical_key':{'name':'source_sample_id','source_field':'metadata.csv:orig.ident','rule':'Exact source string preserved in GSE176078 namespace; no suffix removal, case folding, patient field creation or source-label merging','status':'SOURCE_SAMPLE_KEY_SUPPORTED','source_sample_count':26,'separate_patient_key':'ABSENT','patient_id_assignment':'PROHIBITED_WITH_CURRENT_EVIDENCE','library_id_assignment':'NOT_ESTABLISHED','capture_batch_id_assignment':'NOT_ESTABLISHED','reason':'All 26 exact orig.ident values match 26 producer GEO Sample_title records; generic library protocols and 26-tumor cohort narrative do not supply a row-level donor/library/well crosswalk.'},
 'source_evidence':{'GEO_raw':'01_inputs/source_metadata/GSE176078_family.soft.gz','metadata':identity['metadata_file'],'GEO_review':'00_plan/S1-to-S2-entry-evidence.v1/GEO-metadata-identity-evidence.v1.json','PMC_existing':'01_inputs/literature/PMC9044823-BioC.xml','PMC_current':'00_plan/S1-to-S2-entry-evidence.v1/PMC9044823.1.source.v1.xml','PMC_plugin_return':'00_plan/S1-to-S2-entry-evidence.v1/PMC-plugin-stdout.v1.json','supplement_failure':'00_plan/S1-to-S2-entry-evidence.v1/PMC-supplement-failure.v1.json'},
 'alias_review':{'left':{'namespace':'Zenodo4739739_Visium','source_sample_id':'CID4290'},'right':{'namespace':'GSE176078_scRNA','source_sample_id':'CID4290A','GEO_accession':'GSM5354523','BioSample':'SAMN19546327'},'status':'PENDING','action':'KEEP_SEPARATE_NO_ALIAS','reason':'Paper explicitly names CID4290 in the scRNA cohort but the inspected article body never states CID4290 = CID4290A; GEO names CID4290A. No direct producer crosswalk was obtained. Supplementary Table 1-11 retrieval returned HTTP 404. Non-retrieval is not proof of absence in the unavailable supplement.','shared_patient_proven':False,'distinct_patient_proven':False,'name_similarity_used':False},
 'source_samples':[{'source_sample_id':s,'source_field':'orig.ident','GEO_sample_accession':geo[s]['geo_accession'],'GEO_sample_title':geo[s]['fields']['!Sample_title'][0],'observed_metadata_cells':n,'identity_status':'SOURCE_SAMPLE_KEY_SUPPORTED_PATIENT_LIBRARY_CAPTURE_UNVERIFIED'} for s,n in identity['source_sample_counts'].items()],
 'label_policy':{'source':'producer metadata.celltype_minor','observed_distinct_values':29,'missing_in_current_metadata':identity['missing_minor_label'],'keep_exact_labels':True,'merging_authorized':False,'label_biological_validity':'PENDING'},
 'technical_reference_branch':{'eligibility':'FEASIBLE_AS_VERSIONED_PROPOSAL_ONLY','patient_verified_branch':'verified patient x exact producer celltype_minor; original rule retained','patient_unverified_branch':'source_sample_id (exact orig.ident) x exact producer celltype_minor; balance source samples as a technical proxy only','library_balance_claim':'Do not call source groups verified libraries or captures. Sample/library balancing intent does not establish library identity.','S2A':'Metrics only, no stratified selection','S2B':'PENDING explicit approval of S2A-derived QC thresholds AND chosen stratification/allocation supplement; no reference construction now','patient_level_summaries_and_LOO':'BLOCKED until patient crosswalk verified; preserve planned module as PENDING, do not relabel source-sample summaries as cross-patient validation'},
 'patient_level_inference':'BLOCKED','biological_results':'PENDING','BioNexus_machine_verdict':'PENDING','old_identity_tables':'Preserved verbatim; source patientid strings and UNKNOWN placeholders in old audit tables are not newly verified patient fields.'}
resrel='02_identity/scRNA-identity-resolution.v1.json';put(resrel,resolution);resh=sha(R/resrel)
free=shutil.disk_usage('C:\\').free;observed=stamp()
supp=f'''# SpatialWarrant S2A 技术 QC 补充 v1

状态：PROPOSED_AWAITING_HASH_BOUND_HUMAN_APPROVAL。此文件只细分 S2 的入口与技术 QC 范围，不是本次计算授权。
父方案：00_plan/analysis-plan.lock.md；SHA-256：{PLAN}。
身份裁决：{resrel}；SHA-256：{resh}。
创建时间：{observed}。全部数据、临时文件、输出、日志和审计记录均位于 C:\\Plugin\\BioNexus\\review\\spatialwarrant-run-01。

## 不变的科学合同

原 S0–S7 锁定方案及 claim 原文保留；拒绝的 D 盘 storage-only v2 和失败写入检查保留为 NOT_APPROVED 历史。此次补充不改变主问题、主终点、独立单位要求、几何定义、停止条件或证据边界。
完整保留 GSE176078 参考、六张 Zenodo Visium、空间域、Tangram、marker/NNLS、scanpy ingest、niche、LIANA、10x 技术迁移、BioNexus ledger/debt、过度解读测试与 S7 产物。未执行模块保持 PENDING，不能因身份未明而删除。
主边界只由发布者病理区域、组织掩膜和空间几何定义；免疫比例、表达、聚类、去卷积及文献都不能决定主边界。

## 输入与身份

未来 S2A 只使用已索引的 GSE176078 count_matrix_sparse.mtx、count_matrix_genes.tsv、count_matrix_barcodes.tsv 和 metadata.csv。这里的“原始计数”指发布者处理后、已做发布者 QC 的整数 UMI count 层，不是未经细胞筛选的液滴全集或 FASTQ。不能恢复被发布者排除的细胞。
当前发布矩阵声明 29733 genes × 100064 cells；26 个 orig.ident 与 GEO 的 26 个 Sample_title 精确匹配。该对应只支持 source_sample_id。禁止创建 patient_id，也不能声称 orig.ident 已证明为单个文库或捕获批次。
保留 CID4290 与 CID4290A 原样、分开命名空间，别名 PENDING；分开标识也不证明它们来自不同患者。保留 producer celltype_minor 原字符串，不重注释、不合并。旧 patient_id/section_id 审计列中的占位或来源字符串不能被当作已核实患者/切片主键。

## S2A：仅指标计算，完成后停止

仅在人工批准本补充的 SHA-256 后才可执行，路线为 **local Python execution**，不是 NGS registered workflow run。只使用已可用的本地依赖；缺失或不兼容时停止，不安装。

1. 重核父方案、补充及输入精确字节哈希；重核 C 盘空间并执行仅临时新文件的非破坏性写入/读回检查。现有文件一律只读。矩阵以稀疏或流式形式读取，禁止稠密化或复制大型输入。对所有计数做整数、有限、非负、索引范围及维度一致性检查；检查重复坐标，不得无声折叠或改变特征。S1 只检过 MatrixMarket 声明，没有声称已扫描所有数值。
2. 用 barcode 一对一连接元数据，保留全部输入细胞；不因指标、零 UMI、缺失字段或作者标签选择细胞。关键条码歧义、重复或不一致为硬停止。缺失的非关键字段只能标记缺失，不能推断身份。
3. 对每个细胞计算 total_UMI = 全部输入基因原始计数之和；detected_genes = 原始计数 > 0 的输入基因数；mitochondrial_percent = 100 × 线粒体基因 UMI / total_UMI。total_UMI = 0 时该比例为缺失，并保存 zero_UMI 标志，不能填成 0%。
4. 线粒体集合仅以当前人类基因符号表中大小写精确的 MT- 前缀确定，先保存完整成员、索引及哈希；不用表达挑选基因，不扩展别名。若符号模式/物种不兼容、集合为空或特征映射存在歧义，停止相应指标并报告，不能伪造比例。有效集合下真实 0 计数与缺失必须分开。
5. 每个 source_sample_id 输出每细胞指标及样本内 n、有效/缺失/零值数、最小值、最大值、中位数与固定分位数（1%、5%、25%、75%、95%、99%），保持分母与有效值计数明确。使用未改变的原始指标，不把作者已有 nCount_RNA/nFeature_RNA/percent.mito 当作本次重算结果。只做技术分布汇总，不计算组间检验、患者效应或细胞类型生物学比较。
6. 只报告检测基因数、UMI、线粒体比例及缺失情况，以及保证其可解释性所需的输入/身份一致性记录。数值 QC 阈值保持 PENDING，待这些分布产生后另建版本化阈值提案，逐样本给出理由和预计保留数，提交人工批准。S2A 不应用阈值，不生成已过滤细胞集。

S2A 明确禁止过滤/删细胞、抽样、HVG、归一化/log1p、PCA、Leiden、整合、doublet/ambient caller、marker 解释、细胞标签评估、参考矩阵构建、空间数据加载分析、S3、任何主终点计算或生物学解释。无需安装 S2–S6 依赖。
未来产物目录提案：03_reference/S2A_metrics.v1/（本次不创建）；其中包含 per-cell-QC.v1.csv、per-source-sample-QC.v1.csv、missingness.v1.json、mitochondrial-feature-mask.v1.json、input-validation.v1.json、checkpoint.v1.md，以及指向源文件的 manifest 和哈希。qc-threshold-proposal.v1.json 在指标产生后才能另建，状态必须 AWAITING_HUMAN_APPROVAL。所有输出只新建，冲突即停。

## S2B：过滤及技术参考构建的单独门槛

当前为 PENDING，不包含在 S2A 批准中。必须先由人工批准 S2A 的数据依赖 QC 阈值，冻结具体过滤规则、缺失处置及输入/阈值哈希，再明确批准 S2B 的分层键与可行分配。
患者映射若已由明确来源核实，保留原 verified patient × producer celltype_minor 分层；若仍未核实，可另行批准 source_sample_id（精确 orig.ident）× producer celltype_minor 的**来源样本平衡技术参考**分支。这只是样本/文库平衡意图下的来源样本代理，不能声称已完成文库平衡、患者平衡或患者级推断。此候选分支不覆盖原患者分层模块；后者等待证据。
S2B 经单独批准后保留 ≤40000 细胞上限、seed 20260904、原稀有标签保留规则、不重复采样、2000 HVG、PCA、数值 Leiden 和标签证据评估；保留可选 Harmony/BBKNN 的条件分支。患者证据未核实时，跨患者评估模块继续 PENDING，不以跨来源样本结果冒充。标签不能合并；分配冲突/身份歧义必须先复核。此次不选择数据依赖阈值、抽样细胞或调整任何科学参数。

## 阶段性阻断与存储

病理标签映射未冻结、10 个组织外条码的分析排除名单尚未冻结、物理 section/组织区域关系及坐标注册未完成，均不影响单独的 scRNA S2A 指标计算，也不自行否定候选 scRNA 技术参考；但必须继续阻断 S3。组织外条码分别来自 CID4290（6）、CID44971（2）、CID4535（2）；只能依据发布者 in_tissue 排除，保留原始文件，不能因表达把它们纳入。S3 的标签/掩膜生成仍需来源支持的病理映射与人工检查点。
未知 donor/sample/section 独立性阻断患者推断和独立重复声明；即使以后允许 section 描述，也不能从六个文件束推成六个独立患者。原少于四个已核实独立配对单位时仅描述的门槛不变。
本次空间快照：{free} 字节（{free/1024**3:.6f} GiB），{observed}。S2A 启动时必须重新确认 ≥32212254720 字节（30 GiB）；每次写入前及分块写入期间检查，若 <21474836480 字节（20 GiB）立即停止继续写入，不为保存尾部日志绕过门槛。为有余量时写入预先限制块大小并保留检查点；低于门槛后只在会话报告中说明，恢复须复核。
逐阶段存储预算：旧 S1 预算和实际记录保留；S2A 新增文件总预算上限 1 GiB（技术指标表、轻量日志/检查点/哈希），不复制矩阵、不缓存大型中间对象。它是操作上限而非用量预测；写入会越预算时停止并提交版本化预算修订。S2B–S7 各阶段预算 PENDING，必须在各自获准执行前建立，不借 S2A 许可启动后续阶段。

硬停止：父方案/补充/输入哈希不符；无本补充人工批准；空间不足/越预算；目标文件冲突；计数非有限/负数/非整数或坐标重复；barcode/特征映射不一致；所需依赖不可用；请求越过指标范围；试图以未知患者、合并别名或表达定义边界。遇到停止保留既有文件，记录真实错误，不能宣称完成。
科学结果、效应、显著性、BioNexus machine verdict、分析 RAM/运行时间与 Human Scientific Adjudication 均为 PENDING。计算许可不代表生物学结论被接受。
'''
suprel='00_plan/S2A-technical-QC-supplement.v1.md';put(suprel,supp);suph=sha(R/suprel)
decisions=[
 {'gate':'S1 technical gate','status':'PASS','scope':'S1 acquisition, exact-byte integrity, source identifiers and metadata joins only','reasons':['209 historical artifacts match their S1 SHA-256 inventory; all 123 input entries match hashes/sizes; all 11 required files read in full and matched.','26 source sample IDs, 100064 barcode-aligned metadata rows and 29 exact producer minor labels observed; no missing source IDs/minor labels.','S1 count inspection was header-only. Complete count validation remains S2A work; this PASS does not clear identity, pathology or biological gates.'],'evidence':['S1-checkpoint.md','S1-starting-point-assessment.json','manifest/S1-source-manifest.json','manifest/S1-input-file-index.json','00_plan/S1-to-S2-entry-evidence.v1/S1-artifact-verification.v1.json','00_plan/S1-to-S2-entry-evidence.v1/input-index-crosscheck.v1.json','02_identity/scrna-input-integrity.json']},
 {'gate':'S2A metrics-only entry','status':'PERMITTED','execution_authorized':False,'conditions':['Explicit human approval bound to S2A supplement SHA-256 before execution.','Fresh C start gate >=30 GiB and non-destructive write/read preflight; stop writes below20 GiB.','Only source_sample_id technical metrics, strict raw-count validation, no filtering or biological interpretation.'],'reasons':['Metrics need a stable source grouping, not verified independent patients. Exact orig.ident/GEO sample correspondence and barcode joins support that narrow grouping.','Patient identity, Visium pathology and physical-section gaps do not prevent independent scRNA metrics-only preparation.'],'evidence':[resrel,suprel,'02_identity/scrna-input-integrity.json','00_plan/S1-to-S2-entry-evidence.v1/GEO-metadata-identity-evidence.v1.json']},
 {'gate':'S2B filtering/reference construction','status':'PENDING','execution_authorized':False,'reasons':['S2A has not run; data-dependent QC thresholds have neither been produced nor human-approved.','Original verified-patient stratification cannot currently run. Source-sample x exact producer minor label technical branch is feasible as a proposed versioned supplement only; explicit branch/allocation approval is required.','No inference of patients, no alias normalization, no label merging; original cross-patient module retained pending identity evidence.'],'evidence':['00_plan/analysis-plan.lock.md',resrel,suprel]},
 {'gate':'S3 entry','status':'BLOCKED','execution_authorized':False,'reasons':['Pathology label map remains PENDING_REVIEW_NOT_FROZEN; composite invasive-cancer categories have not been mapped from producer definitions.','CID4290/CID44971/CID4535 have 6/2/2 off-tissue metadata barcodes; explicit frozen exclusion and coordinate/tissue joins remain prerequisites.','Source bundle stems do not prove physical sections; CID44971 has three tissue regions in the paper. Registration and no-cross-section geometry remain unverified.','No expression, clustering, proportions, deconvolution or literature may substitute for producer pathology plus geometry. No automatic S3 clearance after S2A.'],'evidence':['02_identity/pathology-label-map.json','02_identity/pathology-label-inventory.csv','02_identity/visium-integrity-exceptions.json','02_identity/visium-sample-identity.csv','02_identity/identity-gate.json','00_plan/geometry-contract-S1.json','00_plan/S1-to-S2-entry-evidence.v1/PMC-XML-identity-search.v1.json']},
 {'gate':'patient-level inference','status':'BLOCKED','execution_authorized':False,'reasons':['No row-level source_sample -> patient/library/capture crosswalk has been established. Generic cohort patient descriptions and a producer patientid source field do not resolve hierarchy/independence.','CID4290/CID4290A alias remains PENDING; keeping them separate does not establish different donors. 10x overlap also remains unknown.','No patient-level aggregation, cross-patient validation, population CI/p-value or independent replication claim until relevant identities are verified; original >=4 independent paired-unit gate remains binding.'],'evidence':[resrel,'02_identity/identity-gate.json','02_identity/sample-identity.csv','02_identity/visium-sample-identity.csv','00_plan/analysis-plan.lock.md']}
]
manifest=read(R/'manifest/S1-source-manifest.json')
review={'artifact_type':'S1_to_S2_entry_review','version':'1','created_at_utc':stamp(),'parent_plan_sha256':PLAN,'review_scope':'Read-only S1 evidence and entry adjudication; new versioned outputs only','S2A_supplement':{'file':suprel,'sha256':suph,'human_approval':'PENDING'},'identity_resolution':{'file':resrel,'sha256':resh},'decisions':decisions,'required_files':required_records,'storage':{'observed_at_utc':observed,'free_C_bytes':free,'free_C_GiB':free/1024**3,'start_min_bytes':30*1024**3,'write_stop_below_bytes':20*1024**3,'current_gate':'PASS','fresh_execution_preflight_required':True,'new_non_destructive_write_test_this_review':'NOT_RUN_READ_ONLY_REVIEW','S2A_new_storage_budget_cap_bytes':1024**3},'evidence_limits':['No count values parsed, QC metrics computed or biological analysis performed in this review. Byte hashing is integrity-only.','No dependency installation, S2/S3 execution, mask generation, label merging or lock modification.','Published scRNA raw count layer already reflects producer processing/QC; unfiltered droplets were not acquired.','Successful PMC service metadata is callability/source-location evidence; identity conclusions use GEO raw and actual article content.','Supplementary Table 1-11 retrieval failed HTTP404; unresolved is bounded to inspected evidence, not proof that no producer crosswalk exists elsewhere.','No BioNexus warrant_check invoked; technical policy decisions are not BioNexus machine verdicts.'],'literature':{'plugin':'Life Sciences Literature 0.1.5','PMC_script_call':'SUCCESS','current_article_XML_HTTP_status':200,'article_XML_provider_MD5_verified':True,'supplement_HTTP_status':404,'evidence_directory':'00_plan/S1-to-S2-entry-evidence.v1','source_urls':['https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE176078','https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSM5354523','https://pmc.ncbi.nlm.nih.gov/articles/PMC9044823/'],'source_context_not_boundary_input':True},'historical_failures_preserved':[{'provider':x.get('provider_id'),'error':x.get('error')} for x in manifest['failed_attempts']],'plugin_roles':{'Life Sciences Literature':'Actual PMC skill-local script for current metadata/file URLs; raw request/return retained; not identity adjudicator','NGS Analysis Workbench':'S0/S1 data-understanding/design context; no new registered run; no compatible registered downstream workflow in retained catalog snapshot','local Python':'This review: file integrity, metadata evidence and report creation only. Future S2A route: local Python execution','BioNexus':'Passive ledger/provenance/debt/overclaim work retained; historical S1 sidecar unchanged; no new scientific verdict'},'scientific_results':'PENDING','machine_verdict':'PENDING','analysis_resource_usage':'PENDING','biological_conclusion_acceptance':'NOT_GIVEN','stop_after_review':True}
reviewrel='00_plan/S1-to-S2-entry-review.v1.json';put(reviewrel,review)
md=f'''# SpatialWarrant S1→S2 入口裁决 v1

时间：{review['created_at_utc']}。范围：只读核验 S1，并新建评审/补充；本次未启动 S2A、S2B 或 S3。
父方案 SHA-256：{PLAN}（一致，未改动）。

| 入口 | 裁决 | 具体依据与边界 |
| --- | --- | --- |
| S1 technical gate | PASS | 209 个历史文件字节哈希全部匹配；123 个输入索引全部一致；指定 11 文件已完整读取核对。仅通过 S1 输入准备/元数据技术检查，不代表全计数扫描或身份/病理通过。 |
| S2A metrics-only entry | PERMITTED | 稳定的 source_sample_id 足够支持每来源样本 QC 指标；须先人工批准下列补充哈希及启动前复查。此裁决不是启动指令。 |
| S2B filtering/reference construction | PENDING | S2A 尚未运行，数值 QC 阈值尚未产生/批准；来源样本技术参考分支与具体分配亦须另行批准。 |
| S3 entry | BLOCKED | 病理映射未冻结、组织外条码排除未冻结、物理 section 关系及注册未核实。仅靠完成 S2A 不解除这些门槛。 |
| patient-level inference | BLOCKED | orig.ident 不是已核实患者字段；CID4290/CID4290A 别名未证实；sample/section/donor 层级及独立性不明。 |

## 身份证据与决策

GEO 原始 SOFT、metadata.csv 和新建 GEO-metadata-identity-evidence.v1.json 一致显示：26 个 orig.ident 精确对应 26 个 GEO Sample_title；100064 条元数据与条码顺序一致，29 个 producer celltype_minor 标签原样保留。没有来源样本键或 minor label 缺失。固定用 source_sample_id，不制造 patient_id；通用测序建库说明不能证明每个 orig.ident 唯一对应一个文库或捕获批次。
GSM5354523 的标题为 CID4290A、BioSample 为 SAMN19546327。PMC 论文用 CID4290 描述 scRNA/Visium 同队列来源，但正文没有提供与 CID4290A 的明确别名声明。保留分离，状态 PENDING；不能因为相似或差一个后缀合并，也不能因此视为不同患者。
Life Sciences Literature 的 PMC 脚本本次实际成功；其返回的版本化 XML 已获取（HTTP 200），文件 MD5 与返回 URL 提供值一致。原 S1 PubMed 请求/原始 XML、GEO SOFT、PMC BioC 仍保留。补充表入口实际返回 HTTP 404，原始错误响应及请求均已保存。该失败限制身份核实，不能转写成“已阅读补充表”或“别名不存在”。

## S2 的分段与候选技术参考

S2A 只计算每个来源样本内的每细胞 detected genes、UMI、线粒体比例及缺失情况，保留全部细胞；不筛选、不抽样、不归一化、不做 HVG/PCA/Leiden/整合/标签生物学评估。输入是发布者已处理且已做 QC 的整数计数层，不是原始液滴全集。完整数值有效性扫描属于未来 S2A，本次只做文件哈希与元数据核查。
S2B 必须等待人工批准 S2A 数据依赖 QC 阈值。患者若核实，原 verified patient × producer celltype_minor 分层继续有效；患者未核实时，可以另行批准 source_sample_id × producer celltype_minor 的来源样本平衡技术分支，但不能称患者/已核实文库平衡，也不能进行患者级推断。上限 40000、seed 20260904、稀有组约束、HVG/PCA/数值 Leiden、标签证据评估与其他 S0–S7 模块全部保留。原跨患者模块继续等待来源证据，不能以技术样本比较替换。

## 阶段阻断及证据文件

病理映射：02_identity/pathology-label-map.json 为 PENDING_REVIEW_NOT_FROZEN；pathology-label-inventory.csv 保留复合类别。它不阻止 scRNA S2A 或未来独立批准的技术参考，但阻止 S3 的标签/边界锁。不得以免疫比例、表达、聚类、去卷积或文献决定主边界。
组织外条码：02_identity/visium-integrity-exceptions.json 记录 CID4290 6 个、CID44971 2 个、CID4535 2 个。它们不影响 scRNA 指标；进入空间分析前必须根据发布者 in_tissue 冻结排除清单，不能修改原文件或通过表达重新纳入。它们不是永久废弃整个样本的理由。
section 身份：02_identity/visium-sample-identity.csv 与 identity-gate.json 仍只支持来源文件束/标签。当前 XML Figure 6 明确提到 CID44971 三个 tissue regions，不能直接变成三个独立 section/patient。该缺口不阻止独立 scRNA 技术准备，但阻止当前 S3 的物理 section/注册/防跨片几何门槛及患者独立重复推断。
患者推断：02_identity/sample-identity.csv 和本次 scRNA-identity-resolution.v1.json 共同保留未知患者状态。原至少四个已核实独立配对单位的推断门槛保留；少于四个或独立性未核实，只能在未来获准且几何有效时做描述。10x 仍仅技术迁移，不算独立生物学复现。
S1 技术核验详情见 S1-checkpoint.md、S1-starting-point-assessment.json、manifest/S1-source-manifest.json、manifest/S1-input-file-index.json 及新证据目录的两个 verification/crosscheck JSON。primary-program.lock.json 的 196/200（98%）来源标识覆盖门槛保留通过；未计算表达程序或终点。

## 存储、停止与审计

C 盘快照：{free} 字节（{free/1024**3:.6f} GiB），记录时间 {observed}。启动时必须重新满足 30 GiB，并在真正 S2A 启动前做非破坏性写入检查；本次只读评审不另做临时写入试验。运行中低于 20 GiB 立即停止继续写入。S2A 新增产物预算上限 1 GiB，是操作上限而非资源预测；其余各阶段预算执行前另建。
硬停止条件：无补充哈希批准、哈希变化、空间/预算不足、输出冲突、条码/特征歧义、非整数/负数/非有限计数、依赖不可用或请求越过 metrics-only 范围。原全计划停止条件继续有效；S3 还须先解决病理映射、组织外条码及空间注册/section 门槛。不会借用 S2A 许可继续 S2B/S3。
只新建文件，原方案、plan.sha256、D 盘 v2/失败检查、NOT_APPROVED 记录和全部旧预演均保留。Life Sciences Literature 是真实来源检索；NGS 是设计/可行性上下文；本地 Python 承担当前字节核验与未来技术计算；BioNexus 保留被动审计角色。当前没有 NGS registered workflow run，也没有 BioNexus 科学 Warrant 裁决。
所有科学结果、分析资源预测、机器 verdict 与生物学结论接受状态保持 PENDING/NOT_GIVEN；本表是阶段入口政策判断。

## 可供人工批准的唯一执行范围

补充文件：{suprel}；SHA-256：{suph}。
身份裁决文件：{resrel}；SHA-256：{resh}。
当前审批状态 PENDING；若人工批准，只执行此补充的 S2A 技术指标计算，完成指标/检查点后停止。S2B、S3 及患者级推断均未获准。完整机器可读证据、条件与逐项文件列表见同名 v1.json；四份交付的 SHA-256 见 S1-to-S2-entry-review.v1.sha256。
'''
mdrel='00_plan/S1-to-S2-entry-review.v1.md';put(mdrel,md)
files=[mdrel,reviewrel,suprel,resrel]
put('00_plan/S1-to-S2-entry-review.v1.sha256',''.join(f'{sha(R/n)}  {n}\n' for n in files))
put('00_plan/S1-to-S2-entry-evidence.v1/review-read-checks.v1.json',{'required_files':required_records,'created':stamp(),'review_setup_issues':[{'event':'Initial UTF-8 plan read attempted with Windows default GBK; UnicodeDecodeError; resolved by explicit utf-8-sig.','source_effect':'No source file changed; full read succeeded before adjudication.'}],'historical_artifact_index_sha256':sha(R/'manifest/S1-artifact-index.sha256')})
for fn in ['entry_review_collect.py','entry_review_fetch_xml.py','entry_review_publish.py']:
 p=pathlib.Path(__file__).with_name(fn)
 with (E/fn).open('xb') as f:f.write(p.read_bytes())
put('00_plan/S1-to-S2-entry-evidence.v1/evidence.sha256',''.join(f'{sha(p)}  {p.name}\n' for p in sorted(E.iterdir()) if p.is_file()))
print(json.dumps({'files':[{'file':n,'sha256':sha(R/n)} for n in files],'free_C_bytes':free,'status':[{'gate':x['gate'],'status':x['status']} for x in decisions]},ensure_ascii=True))
