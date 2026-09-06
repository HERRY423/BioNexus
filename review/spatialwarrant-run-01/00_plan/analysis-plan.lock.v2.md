# SpatialWarrant — analysis-plan.lock.v2.md

Plan version: SW-R01-S0-v2 (storage-only amendment)
Plan lifecycle: STORAGE_REVISION_AWAITING_APPROVAL; S1_NOT_AUTHORIZED
S0 scientific-design and v1-hash review: manually checked by the user in the current task.
Storage-v2 approval / S1 execution approval / scientific results / analysis resource usage / machine verdict / Human Scientific Adjudication: **PENDING**
Inspection date: 2026-09-05 UTC (2026-09-04 America/Los_Angeles)
Control and audit root: C:\Plugin\BioNexus\review\spatialwarrant-run-01
Large-artifact root: D:\SpatialWarrant\spatialwarrant-run-01
Current permission: storage-location amendment, conflict/writeability inspection and new v2 preregistration files only; no S1 authorization.
Execution route: **local Python execution**. NGS registered workflow run: **PENDING; no run exists**.


## Storage amendment record and precedence

This is the single storage-only revision requested by the user after manual review of the S0 scientific design and v1 plan hash. It changes storage routing, capacity thresholds and storage-approval wording only. Scientific questions, methods, all S0–S7 modules, claims, scientific stopping conditions and evidence boundaries are preserved. Sections 4–8 and the original claim CSV are text-identical to v1. Scientific result, resource-use and verdict fields remain PENDING.

History retained without overwrite in the control 00_plan directory:
- analysis-plan.lock.md (v1): SHA-256 854e2d06eb25903a870606934964fd8b7f0a40a16a9658ef565cf5ab14a03c82
- plan.sha256 (v1): SHA-256 9939eaa435dcdd3a4e2a8ba77bdc88cfe65922582646fb3adc167a6a7dab8469
- plugin-capability-check.json remains the original S0 evidence snapshot, unchanged.
- storage-location-check.v2.json: SHA-256 0d3c99f0cb4664f08645751bbaff95a86ccbefe9b4fe6b2ca06b8e052aa1211a

Current storage inspection: C available 2986307584 bytes (2.781 GiB); D available 340869963776 bytes (317.460 GiB). These are measured host-capacity snapshots, not project resource usage or future runtime/peak estimates. The D target did not exist and no collision was observed. Its creation failed with Windows Access denied under the current Windows user even outside the Codex filesystem sandbox; therefore the write/read probe was not reached and writeability is NOT_ESTABLISHED. No probe/data file, directory migration, ACL modification or scientific output was created on D. See the hash-bound storage check for exact failure evidence.

D capacity meets the requested 30 GiB threshold at this snapshot, but storage readiness is not complete: the target must be provisioned with suitable access by an authorized administrator, then conflict and write/read checks must pass. Do not reinterpret the failed creation as successful writeability. This document authorizes no ACL change or S1 work.

For all inherited relative artifact paths below, section 9 supplies the two-root mapping. Earlier S0 observations in sections 1–3 remain historical; their original C-capacity/run-approval rows are not current v2 readiness. Any inherited phrase about approval before S1 means a separate, explicit future S1 execution approval, never approval of this storage-only amendment. Section 11 defines the current approval boundary. The old 10 GiB storage policy is superseded only by the expressly requested D thresholds in section 9; all non-storage stops remain unchanged.

## 1. Authority, immutable inputs, scope

The user-designated ANALYSIS_PLAN_LOCK.md and CLAIMS_PREREGISTERED.csv are binding. The full S0–S7 design is retained. No scientific dataset, analysis family, method sensitivity, technical transfer, audit, overclaim test, screenshot concept, or English submission artifact is removed.

Authoritative source directory: C:\Plugin\BioNexus\review\spatialwarrant-revised-design

- ANALYSIS_PLAN_LOCK.md SHA-256: f8d955c041f1612dbe979b59b5bde150ee333208d90525da20b276299083b327
- CLAIMS_PREREGISTERED.csv SHA-256: 552fa77e9ba76fd83e6b000677cd322f4b64ea4c6c4ab46e45ea97e81f0736e3
- WORKBENCH_EXECUTION_GUIDE.zh-CN.md SHA-256: ef0b6329017a8fbc61cb1f2a6277e2ac6536d70ac4a6caf0eead663c8b4bcd95
- src/db/seed-data.ts SHA-256: f9c8cf869b3729f015f6ceddec0ec63eaad454fdb96fbee995a9b46b859f05b6
- plugin-capability-check.json SHA-256: 15f9863ab4df0c2deb4bed64d726e6e400be28f10f7ad3307826877404a47785

The working Downloads directory contains matching copies of the two authoritative files. Both inspected design directories contained 37 files / 111480 bytes and no .h5/.h5ad/.mtx/.rds/.tar.gz matrix/archive inputs. This is a scoped inventory, not a machine-wide search. The run root did not exist at inspection. No prior rehearsal or source file is overwritten.

The guide and seed-data describe additional retained details; their old predicted runtime/RAM, assumed patient/subtype labels, predetermined refusal/success screenshots, and speculative conclusions are not evidence and cannot populate results. If a descriptive guide phrase conflicts with the source lock's identity gate, the stricter source lock governs. Plan B remains a historical idea, not an authorized substitution for any S0–S7 module.

New choices resolved by this preregistration: primary distance 2 spot spacings, explicit boundary/core disjointness, exact gene-set release target, primary score and pairing algorithm, and resource/parameter gates below. The user reports manual review of the S0 design and v1 hash; these scientific choices remain unchanged and were chosen without opening expression matrices or viewing project results. This storage-only revision does not authorize S1.

## 2. NGS StartingPointAssessment

Applied NGS Analysis Workbench understand-ngs-data and design-ngs-analysis skills, AnalysisContext and relevant single-cell references. These are skill capabilities, not separate MCP analysis services. This document contains the starting_point_assessment and analysis_plan artifacts; it is not a Workbench immutable execution plan.

Known objective: compare the prespecified immune/IFN program at a pathology/geometry-defined tumor–stroma boundary versus tumor core across six public Wu-study Visium sections.

Material inventory and evidence states:

| Material | Role | Observed state / remaining gate |
| --- | --- | --- |
| GSE176078 processed scRNA raw counts and author metadata | Same-study reference; patient × author-label stratification | Planned by source lock; local files absent. BioNexus search_geo responded with zero datasets; GEO web page returned browser challenge. Accession/file contents and scRNA-to-Visium identity remain unknown. |
| Zenodo 4739739 v1 | Six planned Visium sections; counts, coordinates, H&E, producer pathology | Publisher landing page observed. Lists raw/filtered count archives, spatial archive, metadata and annotated H&E PDF. Actual file contents/joins/independence remain unknown. |
| 10x Human Breast Cancer, Block A Section 1 | Technical transfer only | Official landing page reached; input files, chemistry/reference compatibility, absence of cohort overlap and pathology truth remain unknown. |
| MSigDB HALLMARK_INTERFERON_GAMMA_RESPONSE, M5913, human, target release 2024.1.Hs | Prespecified primary program | Official gene-set identity and release documentation observed. Exact versioned GMT contents, membership, license/access and SHA-256 remain PENDING. |
| LIANA interaction resource; PROGENy/Hallmark; knowledge queries | S6 secondary inference/context | Not acquired; versions and successful retrieval PENDING. |
| Existing dashboard/seed data | Plan tracker only | Read as design source; not started, built, installed or used as results. |

Metadata-only sources inspected, no dataset/archive/GMT downloaded:
- Zenodo: https://zenodo.org/records/4739739
- GEO attempted: https://www.ncbi.nlm.nih.gov/geo/query/acc.cgi?acc=GSE176078 (challenge, not verification)
- 10x: https://www.10xgenomics.com/datasets/human-breast-cancer-block-a-section-1-1-standard-1-1-0
- Gene set: https://www.gsea-msigdb.org/gsea/msigdb/human/geneset/HALLMARK_INTERFERON_GAMMA_RESPONSE
- Version source: https://docs.gsea-msigdb.org/MSigDB/Release_Notes/MSigDB_2024.1.Hs/

Supportable tasks are conditional on identity, integer raw counts, feature/barcode joins, registered geometry, reference compatibility and runtime gates. No scientific outcome is observed. The single immediate user decision is whether to approve this hash-bound storage-only v2 amendment; S1 requires separate explicit authorization and all existing entry gates.

## 3. Live capability and runtime readiness

| Component | Actual observation | Real role / limitation |
| --- | --- | --- |
| NGS Analysis Workbench 0.2.16 | MCP list_workflows, list_compute_targets, get_runtime_environment and two list_workflow_versions succeeded | Data understanding, design and live feasibility checks; no analysis executed |
| Live catalog | 12 entries, include_archived=true; no compatible processed-matrix-to-project-endpoint entry | scrnaseq nf-core 4.2.0 and bundled STARsolo both FASTQ-to-count; cannot relabel either as the requested downstream workflow |
| BioNexus 1.0.0-rc.4 | MCP search_geo callable but empty; read-only doctor returned tier full and scverse/spatial available flags | Passive provenance/ledger/debt/audit later; flags are limited package checks, not full-project readiness or scientific verdicts |
| Life Sciences Literature 0.1.5 | Skill script ran; initial ConnectionError; one outside-restriction retry returned PubMed einfo ok=true | Metadata callability proven; Wu paper retrieval/synthesis remains PENDING |
| Life Sciences Databases 0.1.5 | Reactome skill script ran; ConnectionError then HTTPError on one retry | Live Reactome retrieval unresolved; STRING/Open Targets/UniProt endpoints not individually probed, remain PENDING |
| Local Python | C:\Users\13264\anaconda3\python.exe, Python 3.13.9 | Future custom local Python/scverse execution; no scientific analysis now |
| Dependencies | Scanpy 1.12.2, AnnData 0.13.1, Squidpy 1.8.3, CPU Torch 2.13.0+cpu, PyDESeq2 0.5.4 metadata present; tangram-sc/liana/decoupler absent | Required installation and import/end-to-end compatibility unresolved; no installation attempted |
| Controllers/containers | Nextflow/Snakemake absent on observed PATH; Docker daemon unreachable | No compatible registered workflow, so do not install controllers merely to claim plugin execution |
| Capacity | Observed RAM total 33752997888 bytes; available 16132886528; C drive free 3080540160 bytes at probe | Host capacity only; all project resource use and peaks remain PENDING |
| Run/approval | No workflow plan/run or scientific result created; only 00_plan will be published | Approval PENDING; stop at completion of S0 |

Raw calls, errors, versions, timestamps, catalog entries and runtime snapshot are in plugin-capability-check.json. Runtime snapshot runtime-3cb24b1ada8444bd9ae1b3820049961d expired at 2026-09-05T05:58:27.599399Z; it is historical inspection evidence and must be refreshed before future execution.

BioNexus doctor was called via its read-only run_doctor() function because the scripts/doctor.py entry point writes .bionexus-doctor.json. This honors the user's read-only scope. The Python import origin is C:\Plugin\BioNexus\src\bionexus\__init__.py with runtime version 1.0.0-rc.4; distribution metadata also reports an older bionexus 2.7.0. Do not equate distribution metadata, cached plugin, local source and MCP server code identity. Server identity/receipt readiness remains PENDING. Local shell BIONEXUS_MCP_AUDIT_LOG is not configured; server configuration was not established. No host_probe, warrant_check or evidence adjudication was run.

Literature and Databases use skill-local Python scripts, not dedicated MCP endpoints in the exposed surface. Their execution through Python must still retain the actual plugin script/version and raw return. Successful service metadata is checked_sources only, not scientific evidence. Other installed or recommended plugins have no claimed project use.

BioNexus remains passive: it receives completed evidence plus host/human-supplied relationships, checks them deterministically, and cannot become an autonomous planner, scheduler, labeler or final scientific decision-maker.

## 4. Scientific model and identity gates

Primary question: across the six public Wu breast-cancer Visium sections, is the paired difference in the frozen immune/IFN program at the tumor–stroma boundary versus core directionally consistent?

- Observations are spots. Spots, cell counts, regions and technical sections are not independent biological replicates.
- Intended independent unit is a verified patient/sample. Always write **six sections** until source metadata establishes patient–sample–section mapping.
- sample-identity.csv must include patient_id, sample_id, section_id, subtype, processing_lab, modality, source_field, source_record/file, source checksum, verification_status and reason. Unknown stays unknown; neither filename nor accession alone establishes independence.
- Verify raw count integer/nonnegative state, genome/annotation/identifier type, chemistry, library/capture origin, producer-label provenance, section uniqueness, and scRNA/Visium/10x overlap.
- Repeated sections within a sample and repeated samples within a patient are nested. For the primary effect: compute each section pair, average section differences equally within sample, then sample differences equally within patient; weight independent patients equally in the final estimate. Retain all section/sample estimates.
- If verified distinct samples are not proven to come from distinct patients, do not treat them as independent patient replicates. Unknown identity permits section-level descriptive differences only, without a population interval/p value.
- Fewer than four verified independent paired units: block population-effect inference and provide a descriptive case series. All other retained modules remain planned; failure is recorded, never silently removed.
- With at least four verified paired units, inference is still small-sample/study-bound, not a general clinical population guarantee. Subtype or lab confounding cannot be solved by relabeling sections or by visualization batch correction.
- The reference and producer pathology come from the same study. Producer pathology is an orthogonal reference, not independent ground truth.

## 5. Expression-blind geometry lock

The primary boundary is **tumor-side invasive-cancer spots within 2 spot spacings of the producer-defined tumor–stroma interface**. Distances 1 and 3 are prespecified sensitivities. Neither a stromal-side band nor a niche-selected band is substituted as the primary boundary.

Geometry inputs may contain only producer pathology classes/regions, tissue membership and registered spot coordinates. Counts/UMIs are used only later for eligibility, never to place or tune the interface. Prohibited boundary inputs: immune/stromal proportions, any expression/IFN genes, clusters, Tangram, NNLS/markers, ingest, niche, DE, pathways and literature.

Frozen construction:
1. Resolve barcode ↔ coordinate ↔ producer-label joins one-to-one. Retain unassigned/ambiguous labels as excluded with reasons; no inferred biological labels.
2. Record the exact producer codes mapped to invasive cancer and stroma in pathology-label-map.json, based on publisher definitions only, before any boundary/core expression inspection. If no supported mapping exists, stop the main-boundary module.
3. Validate image-coordinate registration, axis order, scalefactors, tissue mask and hex-lattice geometry. Define d as the median positive nearest-neighbor center distance on valid in-tissue coordinates, recording units and lattice check. Adjacency: expected first-ring lattice neighbors with Euclidean distance in [0.8d,1.2d]; no links across a hole or between sections.
4. Operational interface: shared Voronoi cell edges between immediately adjacent producer invasive-cancer and stroma spots, clipped to valid tissue cells. This uses only producer labels plus geometry and applies identically to all sections. Retain publisher polygons as source evidence/overlay if supplied; do not switch algorithms after results.
5. For each invasive-cancer spot, D is the shortest Euclidean distance from its center to an eligible interface edge, divided by d. No interface or unresolvable geometry means no valid mask.
6. Primary boundary B2 = {tumor spots with D ≤ 2}; core C = {tumor spots with D > 3}. Sensitivity B1 uses D ≤ 1; B3 uses D ≤ 3. The strict core inequality removes overlap at D=3 while satisfying the source rule of at least 3 spacings. The 2 < D ≤ 3 band is omitted from the primary comparison. Stroma-only, non-invasive, unknown and off-tissue spots do not enter the primary pair.
7. Save all masks and a coordinate-only overlay, algorithm/config/version, geometry inputs, timestamp and SHA-256 **before primary gene expression inspection and before domain/deconvolution/niche interpretation**.
8. Eligibility then requires at least 20 included spots and at least 100000 total raw-count UMIs in each section-region pseudobulk. Report counts/UMIs/exclusions per section and per distance. A failed threshold excludes that pair, not a reason to widen masks. Stricter thresholds require a documented expression-blind amendment; never loosen thresholds for a favorable result.
9. Report sensitivity both on a common set of eligible independent units across distances and on each mask's eligible set; denominators must be explicit. No mask selection by effect, p value, composition or sample retention.
10. Any later label/registration correction invalidates dependent masks and results; preserve old artifacts, explain the correction, supersede the lock and obtain review before rerunning.

UMI eligibility is expression-dependent quality control and must be disclosed, but cannot alter geometry or use target-gene values. Frozen code should enforce that the geometry function never receives an expression matrix.

## 6. Primary endpoint and statistical lock

Program identity: human MSigDB HALLMARK_INTERFERON_GAMMA_RESPONSE / M5913, release **2024.1.Hs**. This is a fixed historical version chosen for reproducibility, not a claim that it is the latest. Obtain the official versioned H collection GMT, select this exact set and store full original file plus sorted membership, source URL, release, mapping rules and SHA-256 before viewing boundary/core expression. If access/version cannot be verified, stop the primary endpoint; do not replace it with the six-gene display panel.

Feature policy: preserve integer raw counts. Map feature IDs using documented reference metadata to unambiguous human gene symbols; sum genuinely duplicate features mapping to the same gene, never resolve ambiguous aliases using expression. Freeze a common gene-set/feature-ID intersection across all six planned sections without reading expression values. Require ≥90% of the versioned set identifiable in every section; list every missing/ambiguous member. If the gate fails, seek an amendment rather than dynamically shrinking the set after outcomes. Zero counts for an identifiable gene remain zero.

For section s and region r:
- Y_srg = sum of raw UMI counts over included spots for gene g.
- L_sr = total raw gene-expression UMIs across all retained gene features in that region (exclude non-gene-expression feature modalities).
- P_sr = mean over the frozen program genes of log2(1 + 1000000 × Y_srg / L_sr).
- Section paired effect Δ_s = P_s,boundary − P_s,core, in mean log2(CPM+1) units. This is not automatically a log2 fold change.
- Follow the section→sample→patient averaging rule in section 4; aggregate effect is the unweighted mean of verified independent-unit Δ values.

Report all Δ values, aggregate estimate, actual denominator, positive/negative/zero direction counts, exclusions and reasons. No expected sign is registered. If identity and n≥4 gates pass, report a two-sided 95% Student-t interval on independent-unit Δ values, stating the approximate normality assumption and small-n limitation. Also report an exact two-sided sign test on nonzero independent-unit differences as a secondary directional diagnostic; list zero ties separately. No gene/spot bootstrap may inflate the sample size. If independence is unverified, the population interval and test remain uncomputed, with descriptive section values only.

Report leave-one-independent-unit-out aggregate estimates (and leave-one-section-out descriptive sensitivity); leave out all sections of a patient together for independent-unit sensitivity. Repeat the frozen score for B1/B2/B3. Do not equate directional count, interval exclusion or a small p value with ROBUST/SUPPORTED or independent validation.

Secondary fixed display: CXCL9, CXCL10, CXCL11, IDO1, STAT1, IRF1. Report every member, including unavailable/zero/non-significant values, with no predicted upregulation. This panel cannot replace the primary program or select a boundary.

Exploratory whole-gene DE: integer raw-count pseudobulk, PyDESeq2, region contrast boundary versus core; use ~ section + region only when section independence is established for inference. If patients repeat, sum raw counts into patient×region and fit ~ patient + region, reporting the change in estimand from the equally weighted primary score. If identity is unknown, the section design may be prepared and descriptive effects reported, but inferential p values/FDR are not presented as valid biological inference. Require full rank, adequate replication and non-confounded pairing. Freeze expression-independent design; low-count filter is ≥10 counts in at least 4 pseudobulk libraries, applied without using effect sign or region preference. Record size-factor method, dispersion/convergence diagnostics, excluded genes and actual tested universe. BH-adjust across the full tested gene set; q<0.05 is only a reporting convention, not an evidence verdict. Preserve all rows, not just significant rows. Secondary tests and spatial metrics never redefine the primary endpoint.

## 7. Full retained S0–S7 program and checkpoints

### S0 — environment and preregistration

Read authoritative files; inspect project, actual plugin surfaces, live catalog, local runtime/dependencies/capacity; apply NGS data understanding/design skills; write this package and hashes. No downloads, package/environment changes, dataset analysis, workflow registration/plan/run, dashboard launch, scientific verdict or publication. Stop for approval.

### S1 — inputs, provenance, identity and resource freeze

After hash-bound approval, next action is **S1 only**, beginning with storage/readiness and source metadata. Preserve GSE176078, Zenodo 4739739, 10x Block A Section 1, fixed MSigDB release, LIANA/pathway resources and knowledge-source returns in the scope.

For every later acquired file: URL/provider identifier, exact version, provider byte count/checksum if supplied, actual transfer byte count/timestamps, local SHA-256, raw success/failure log. Inspect archive membership for traversal and conflicts before extraction; never overwrite existing artifacts. Unavailable provider checksum remains unavailable, not fabricated.

Use Literature for actual Wu paper design/PMID/DOI verification; one retry after failure, preserve both attempts. Service einfo success from S0 does not fulfill this task. Resolve identity table, annotation map, reference build and feature mapping. Freeze gene-set membership/resource versions and geometry-only algorithm config before expression inspection. LIANA resource exact release/hash is required before that module.

No synthetic completion of missing metadata; no inferred subtype or patient count. BioNexus provenance sidecars provide technical integrity only. Write S1-checkpoint.md with completed/failed/unknown items and actual measurements only after execution, then stop for human inspection. No automatic S2.

### S2 — scRNA reference

Retain ≤40000 cells stratified by verified patient × producer celltype_minor, with deterministic seed 20260904. No duplication/oversampling of rare cells. Preserve up to min(200, available QC-passing cells) per producer rare label when feasible; allocate remaining capacity reproducibly across patient×label strata. If reserved cells exceed 40000 or identity/label mapping is ambiguous, pause to freeze a feasible allocation rather than invent cells/labels. Save selected barcode list, stratum counts and seed.

QC: inspect per-capture detected genes, total UMIs and mitochondrial fraction; choose/record standard-metric thresholds without boundary effects, keep pass/fail flags. Numerical data-specific thresholds must be frozen in a QC supplement and reviewed at the stage checkpoint. Doublet/ambient evidence limitations remain explicit; no unrequested caller is silently substituted. Preserve raw counts; sparse normalization/log1p for exploratory embedding only. Retain 2000 batch-aware HVGs, PCA, numerical Leiden, author-label evidence/purity/marker/cross-patient summaries and reference EvidenceCard. Optional Harmony/BBKNN remains a conditional, separately recorded sensitivity branch; never use corrected embeddings/counts for primary pseudobulk. Labels are producer annotation, not AI identity calls. Any coarse-label merge needs a recorded mapping, not unlogged biological judgment.

Route is local Python/scverse execution unless a later live catalog actually supplies a compatible entry and a newly approved execution plan runs it. Do not claim NGS registered workflow run for local scripts.

### S3 — Visium QC and domains

For all six sections validate raw counts, genes/barcodes, coordinate completeness, tissue membership, pathology coverage and missingness. Freeze section 5 masks before expression-based interpretation. Preserve QC and separate geometry eligibility from count eligibility.

Retain expression-derived numeric Leiden spatially displayed domains with resolutions 0.3/0.4/0.5/0.6/0.7/0.8, primary display 0.5; no selection by pathology agreement. Record preprocessing/HVG/PCA/neighbor parameters in the stage config before running. Report ARI/NMI on common annotated spots and matching label granularity, six H&E/pathology/domain/mask overlays, Moran statistics and boundary Dice/Jaccard. Domain-versus-pathology metrics are descriptive; no assumed success threshold. Record how cluster labels are matched for overlap, and a geometry edge-pixel/spot tolerance based on d; do not tune this for agreement. Any Moran permutation result requires an explicitly recorded spatial null; spot-level permutations do not establish patient replication.

Write S2-S3-checkpoint.md; stop.

### S4 — method sensitivity

Retain Tangram cluster mode on CPU, clusters aggregated by producer celltype_minor; preserve numeric reference clustering separately. Starting specification num_epochs=500, training-gene display target 1000; retain 500/1000/2000 training-gene sensitivities with seeds 20260904/20260905/20260906. These are parameter choices, not a convergence or runtime prediction. Choose candidate markers from reference-only per-label top-50 ranked genes, deterministically merge/rank and intersect feature IDs with target; if fewer candidates exist, report the actual size and mark an infeasible requested grid size rather than pad or silently redefine markers. Save exact training genes, losses, parameters, failures and outputs per section.

Retain marker/NNLS composition baseline from the same reference with a frozen common label vocabulary and documented normalization. NNLS weights are nonnegative, normalized to comparable composition only when their sum is positive; otherwise leave unknown. Compare Tangram/NNLS per-section composition correlations, absolute differences and residual/unknown components; label results model-derived composition sensitivity. Do not assert calibrated cell fractions.

Retain scanpy ingest as **label transfer only**, preserving author-label origin, nearest-reference ambiguity and numeric-cluster information. A mixed Visium spot label is a transferred similarity label, not a pure cell identity or proportion. Report label agreement/confusion separately; never compute or claim proportion Spearman from ingest. All methods share the scRNA reference and therefore do not provide independent biological validation.

### S5 — niches and technical transfer

Retain cross-section KMeans on compatible composition vectors, k=6,7,8,9,10, seeds 20260904/20260905/20260906. Select the displayed k by silhouette only, with ties choosing smaller k, before looking at boundary enrichment. Report the entire grid, per-section contributions, scaling, section weighting and absent types. Never choose k or cell-type merges by the primary endpoint. Prespecified target components are CAF, CD8 T, macrophage and endothelial; their mapping from producer labels requires explicit provenance, unknown stays unknown.

Retain neighborhood enrichment, co-occurrence, Moran analysis, six-section niche maps and niche-versus-fixed-boundary enrichment. Report section-level descriptive enrichment and any independent-unit summary with the same identity gates; spatial autocorrelation precludes naive spot-binomial population tests. Numeric niches and composition-derived labels cannot alter masks.

Retain 10x technical transfer using the frozen feature mapping/scaling and trained KMeans centers without refitting on held-out data. Verify no known overlap; if unknown, do not assert independent holdout. Without matched pathology and clinical truth, report technical compatibility/assignment only, never biological replication of the named niche.

Write S4-S5-checkpoint.md; stop.

### S6 — primary statistics first, then full extension

Within S6 execute the frozen program endpoint before inspecting DE/LIANA/pathway/literature results; earlier optional modules cannot change it. Target twelve section-region pseudobulks only if all six pairs qualify; report the actual number, not a forced twelve. Complete section 6 effect/interval/direction/LOO/distance reporting, then full exploratory DE/BH tables.

Retain LIANA rank_aggregate with a frozen versioned human interaction resource and the prespecified displays CXCL9/10–CXCR3, CD274–PDCD1, TGFB1–TGFBR family and SPP1–CD44. Exact subunits/complex handling and gene universe must be recorded from the resource. Communication is **inferred**, never causal. Mixed Visium spots do not supply directly observed sender/receiver cell-type expression. Use producer-labeled scRNA for cell-type interaction plausibility and spatial composition for co-location context, keeping these evidence layers separate. Any requested boundary cell-type-resolved LIANA analysis lacking valid cell-type-resolved expression stays PENDING/blocked at execution; do not invent such expression by assigning ingest labels to mixed spots. This preserves the module without misrepresenting its identifiability.

Retain decoupler PROGENy/Hallmark and Reactome/STRING/Open Targets/UniProt queries with versions, parameters, raw returned evidence, tested universe and missing calls. Literature includes top 20 DE genes and top 10 inferred L–R results by a frozen deterministic ranking (BH q then absolute effect then identifier for DE; rank_aggregate then identifier for L–R), plus all prespecified display members and actively checked contradictory reports. Exact queries, date, PMID/DOI and consistent/contradictory/no-report/lookup-failed categories must be retained. A failed search is not no-report. Literature agrees/contradicts/context edges are host/human-adjudicated; literature agreement is not independent reproduction of this cohort result.

Write S6-checkpoint.md; stop.

### S7 — passive evidence audit, debt, overclaim and submission

Retain C1–C6/T1–T2, Claim–Evidence Ledger, EvidenceCard, Evidence Debt graph, provenance, independence/dependency links, overclaim test and English submission thread. Receipts bind inputs, exact outputs, code/config/environment and claim IDs. No hand-edited machine verdict in UI; preserve exact returned status and its object, including negative, partial, unassessed and failed states. Hash self-consistency cannot authenticate a producer or establish biological truth. Deduplicate shared study/reference/derived literature evidence; supplied adjudicated edges must not be invented by BioNexus.

Overclaim tests include a single-section population-wide TNBC mechanism, causal T-cell recruitment and immunotherapy prediction; test actual audit behavior later without preassigning a verdict or manufacturing data. Technical recomputation tests input/output hashes, joins and coordinates only. A failure to reject/limit an overclaim must be reported as an audit defect, not edited for a screenshot.

Named, dated, reasoned Human Scientific Adjudication records accept/accept-with-limits/do-not-accept and cannot raise a machine evidence ceiling. Adjudicator name/date/reasons/signature remain PENDING. The model roles specified in the source remain: gpt-6-astra high/xhigh for S0/statistical challenge/S7/story review; gpt-5.6-sol high for approved S1–S6 implementation/execution/recovery. No claim of a model switch or Sol execution without host/session evidence.

Preserve eight screenshot concepts, with wording corrected to actual outcomes:
1. Workbench question/units/plan/approval.
2. Real catalog capability response and local Python routing.
3. Actual Literature Wu-study return and success/failure.
4. Six-section H&E, producer pathology and geometry-only masks.
5. Tangram/NNLS composition sensitivity with ingest separately.
6. All eligible independent-unit effects (otherwise section case-series values), intervals where valid, LOO and volcano/full DE context.
7. Receipt-backed EvidenceCard, ledger and Evidence Debt.
8. Actual overclaim-test response plus named human adjudication, even if the test fails.

Choose four final images only after evidence review. Preserve the English submission artifact; draft only after blocking issues are resolved, every numerical statement traces to a real file, and actual plugin/local-Python use is stated. Posting/sending is not authorized by this plan. S7 blockers yield a repair list and a checkpoint, not an invented final narrative.

## 8. Claim register and PENDING discipline

All eight entries have initial_status=PENDING, actual_result=PENDING and machine_verdict=PENDING. The following maximum_without_new_evidence fields are inherited **policy ceilings, not actual or predicted verdicts**:

| ID | Stage/class | Preregistered subject | Inherited maximum_without_new_evidence |
| --- | --- | --- | --- |
| C1 | S3 descriptive | Domains versus producer pathology: ARI/NMI, granularity, boundary Dice/Jaccard | STUDY_BOUND |
| C2 | S4 descriptive | Tangram–marker/NNLS composition sensitivity; ingest label transfer | STUDY_BOUND |
| C3 | S5 association | Prespecified CAF/CD8-T/macrophage/endothelial niche enrichment at fixed geometry | TO_BE_COMPUTED |
| C4 | S6 population_effect | Frozen program paired effect, uncertainty, direction, LOO | TO_BE_COMPUTED |
| C5 | S6 causal | CXCL9/10–CXCR3 drives T-cell recruitment to boundary | ABSTAIN |
| C6 | S7 clinical | Boundary signature predicts immunotherapy response | REFUSED |
| T1 | S7 population_effect | One section establishes population-wide TNBC immune-exclusion mechanism | ABSTAIN |
| T2 | S7 technical | Independently recomputable hashes, barcode joins, coordinate completeness | TECHNICAL_ONLY |

The full original CSV is reproduced in the appendix for exact statements/gaps. No policy ceiling is copied into actual_verdict. No claim of CXCL9/10/11 upregulation, significance, SUPPORTED/ROBUST, estimated peak RAM or runtime is made. Download bytes, elapsed time, peak RSS, CPU use and output resource use remain PENDING; observed hardware capacity is separate.

## 9. Output contract and safe execution rules

Two-root output contract (future stage directories are not created by this amendment):

    C:\Plugin\BioNexus\review\spatialwarrant-run-01\
      00_plan\
        analysis-plan.lock.md             # immutable v1 history
        plan.sha256                      # immutable v1 history
        plugin-capability-check.json     # original S0 snapshot
        analysis-plan.lock.v2.md
        storage-location-check.v2.json
        plan-v2.sha256
      checkpoints\                      # lightweight stage checkpoint documents
      logs\                             # lightweight operational summaries only
      manifest\                         # source/environment/storage manifests; D artifact hash index
      10_bionexus_audit\                 # lightweight audit manifests, ledger/debt references and adjudication records

    D:\SpatialWarrant\spatialwarrant-run-01\
      01_inputs\                        # archives, downloads, extracted files
      02_identity\                      # full metadata and joins
      03_scrna_reference\
      04_visium_qc\
      05_boundary_masks\
      06_deconvolution\
      07_niches\
      08_pseudobulk\
      09_liana_literature\
      10_bionexus_audit\                 # bulky source evidence; authoritative control/audit index stays on C
      11_figures\
      12_submission\
      logs\                             # verbose/raw logs and tool payloads
      environment\                      # any later approved large environment/cache artifacts
      tmp\                              # downloads, extraction and analysis temporary files

C stores only plans, checkpoints, lightweight logs/audit records, manifests and hash indexes pointing to D. No matrix, archive, image collection, bulk evidence payload or other large analysis output is copied to C. All existing output artifact families are retained and relocated, not removed. A lightweight C audit record that grows large is represented by its manifest/hash reference to the full artifact on D.

Every D artifact index entry must record artifact_id, stage, absolute D path, relative path under the D root, byte size, SHA-256, input/config/code links and creation timestamp. The C checkpoint/audit ledger points to these entries; a pathname alone is not provenance. Recompute hashes from the actual D files during verification. Missing, moved or mismatched artifacts remain unresolved; never materialize placeholder data on C. No automatic fallback to C is allowed when D is unavailable.

Before any later authorized download/extraction/analysis, explicitly direct its temporary files, caches and large outputs to D; any tool that cannot honor the mapping must stop before execution. No environment variables, package installations or cache migrations are changed by this amendment. The control/audit root remains C throughout.

Expected later artifacts include source_manifest, input sidecars, sample-identity.csv, pathology-label-map.json, feature-map, gene-set lock, ref_40k.h5ad, annotation_evidence.csv, QC tables, immutable 1/2/3 masks, deconvolution/ingest outputs, niche labels/maps, paired-effect and whole-DE full tables, LIANA/resource/literature returns, claim-ledger.json/jsonld, debt_graph.md, adversarial-review.md, human-adjudication record, eight screenshot evidence concepts, four selected images and English draft. Each stage has a checkpoint; each correction gets a new versioned subdirectory and linked predecessor hashes.

Never reuse a rehearsal's outputs as new results, overwrite this lock after approval, overwrite checkpoints, delete old work, or silently skip failed modules. Avoid all-at-once dense matrices; use sparse/section-wise computation and recorded checkpoints. Resource measurements must be observed during future approved execution, not extrapolated from old seed data.

Capacity policy (not a forecast): before S1 begins, D must have at least 30 GiB (32212254720 bytes) available, the exact target must pass conflict and write/read checks, and a documented per-stage storage budget must be established in the C manifest directory. Recheck these facts immediately before S1; this snapshot does not authorize starting it. During execution, if D available space falls below 20 GiB (21474836480 bytes), stop further artifact/data writes and pause active writers; do not continue on C. Check available space before large write/extraction operations, reserve planned write capacity so an operation does not consume the 20 GiB reserve, and monitor it while running. Retain partial artifacts and record a lightweight checkpoint on C without duplicating data. Recovery requires adequate space, reconciled budget and normal checkpoint/approval gates; no automatic cleanup is authorized.

The pre-S1 budget must account for every S1–S7 stage, with fields: stage, starting observed D free bytes, retained inputs, archive bytes, extraction bytes, intermediate matrices, analysis outputs/figures, raw logs/evidence, temporary/cache allocations, concurrent-write reservation, retained prior versions, maximum additional storage allocation, projected remaining free bytes based on that allocation, and measurement/source/assumption for each entry. This is an allocation plan, not a predicted experimental result or a runtime/RAM estimate. Numeric budgets remain PENDING until backed by source file sizes and bounded stage allocations before S1; an unknown or unbounded stage allocation is not a completed budget. Compare actual use with the budget at each checkpoint and stop before an unbudgeted large write. No dataset is downloaded to prepare this v2 amendment.

The former 10 GiB C/destination rule is replaced by the requested D pre-S1 30 GiB and running 20 GiB thresholds. C must still be able to save the permitted lightweight control records; it is never a large-data destination. No automatic cleanup, movement to an unapproved drive, installation, or paid/remote compute is authorized. Define a measured runtime memory limit and checkpoint policy before long execution; do not start if safe allocation cannot be bounded. Actual required/peak RAM and duration stay PENDING.

Before every stage: verify plan/source/capability hashes, input hashes, applicable approval/checkpoint, exact interpreter/code/config/resources and read-only receipt import behavior. No controller installation is required merely because NGS controllers are absent for the chosen local route.

## 10. Hard stops and unresolved items

Global/current stop:
- Storage-v2 package complete → stop. S0 design/v1 hash have been manually reviewed by the user; storage-v2 approval and S1 execution approval remain separate and PENDING.
- Any source/approved plan/hash mismatch, pre-existing destination collision, attempted overwrite or missing required approval → stop and preserve evidence.
- Insufficient measured storage or unresolved required dependency/runtime compatibility → do not download/start that workload; retain the module.
- Any boundary definition contaminated by expression/proportions/clusters/deconvolution/niche/literature, or endpoint changed after outcomes → invalidate affected inference and require a versioned amendment/review.

Main-statistics stops:
- Patient/sample independence unverified → no patient/population inference; descriptive six-section route only.
- Fewer than 4 independent paired units → case series, no population-effect claim.
- Missing raw counts, invalid barcode/feature joins, missing producer pathology/coordinates, unresolved registration/label meaning, no interface or overlapping masks → block affected section/module.
- A region below 20 spots or 100000 UMIs → exclude that pair, report failure, no adaptive geometry.
- Exact gene-set release/membership/hash or ≥90% identifier-coverage gate not satisfied before expression comparison → block primary endpoint.
- Confounded/rank-deficient design, nonconvergence or invalid statistical assumptions → no inferential output for the failed model; preserve diagnostics.
- Mixed spots cannot identify sender/receiver expression → block unsupported LIANA cell-type-resolved claim while retaining the planned module and valid scRNA/context layer.

Audit/submission stops:
- Missing exact raw receipt/hash provenance or failed call cannot be promoted to success or filled from memory.
- Unresolved scientific or receipt-import defect → stop final submission drafting at the repair list; no publication.
- Causal/clinical/population assertions lacking the necessary evidence stay bounded by the source register; actual machine verdict remains whatever the later real receipt returns.
- Human Scientific Adjudication missing → no final scientific acceptance; approval of computation never accepts conclusions.

Open items at S0:
1. User hash-bound storage-v2 approval, separate explicit S1 execution approval, and later named scientific adjudicator.
2. D target writeability is NOT_ESTABLISHED after Access denied; provision appropriate target access and recheck. D must have ≥30 GiB before S1, a completed per-stage storage budget, and a running stop below 20 GiB. No cleanup or ACL changes authorized by this revision.
3. Tangram/LIANA/decoupler installation proposal, exact package lock, binary imports and compatible runtime proof.
4. GSE source file identity and scRNA metadata, patient–sample–section mappings, subtype/lab/chemistry/genome and barcode joins.
5. Exact producer pathology codes/registration and masks/region eligibility, not yet computed.
6. Official 2024.1.Hs GMT membership/hash/feature coverage; LIANA and pathway resource versions/hashes.
7. Data-dependent QC supplement and any optional reference integration/coarse-label mapping before their stage execution.
8. Reactome failed service check, individual database endpoint readiness and actual Wu-paper retrieval.
9. BioNexus local distribution/source distinction, MCP server identity and hash-bound receipt configuration.
10. 10x input compatibility, overlap and pathology truth; boundary cell-type-resolved LIANA identifiability.
All unresolved scientific checks, results, use metrics and verdicts remain PENDING; no readiness observation grants execution permission.

## 11. Single approval sentence and next boundary

The single approval sentence accompanying the final v2 SHA-256 approves only this storage-location amendment: C remains the control/audit root, D holds large inputs/extraction/intermediates/analysis outputs, and D uses the pre-S1 30 GiB and running 20 GiB thresholds. It does not approve S1 or accept any biological conclusion. After producing this package, stop.

S1 can begin only after a separate explicit user execution instruction, a successful D conflict/writeability check, a refreshed ≥30 GiB capacity measurement, the completed per-stage storage budget and all applicable unchanged v1 scientific/runtime/identity gates. Current D writeability failure remains a blocker. The plan does not switch models or start tools for S1.

Approval of storage or exploratory computation does not accept biological conclusions, authorize bypass of storage/dependency/identity gates, authorize later stage transitions without checkpoints, or authorize publication. Once S1 is separately authorized and completed, stop and present S1-checkpoint.md; do not automatically proceed to S2.

## Appendix — exact source claim CSV

```csv
claim_id,stage,claim_class,preregistered_statement,initial_status,maximum_without_new_evidence,blocking_evidence_gap
C1,S3,descriptive,"Report per-section agreement between numeric spatial domains and producer pathology, including ARI/NMI, granularity, and boundary Dice/Jaccard; no success threshold is assumed.",PENDING,STUDY_BOUND,"same-study producer annotation is not independent truth"
C2,S4,descriptive,"Report Tangram versus marker/NNLS composition sensitivity and scanpy-ingest label-transfer agreement without a prespecified success result.",PENDING,STUDY_BOUND,"shared scRNA reference; methods are not independent biological evidence"
C3,S5,association,"Test whether the prespecified CAF/CD8-T/macrophage/endothelial niche is enriched at the frozen pathology-geometry boundary and report every section.",PENDING,TO_BE_COMPUTED,"niche result and cross-section stability not observed"
C4,S6,population_effect,"Test the frozen immune/IFN program for a paired boundary-versus-core effect and report effect size, uncertainty, direction count, and leave-one-section-out sensitivity.",PENDING,TO_BE_COMPUTED,"independent-unit identity and results not observed"
C5,S6,causal,"CXCL9/10-CXCR3 drives T-cell recruitment to the boundary.",PENDING,ABSTAIN,"no perturbation, temporal ordering, or independent causal validation"
C6,S7,clinical,"The boundary signature predicts immunotherapy response.",PENDING,REFUSED,"no treatment outcome, independent test cohort, calibration, or clinical validation"
T1,S7,population_effect,"One section establishes a population-wide TNBC immune-exclusion mechanism.",PENDING,ABSTAIN,"one section cannot support population or mechanistic inference"
T2,S7,technical,"Input hashes, barcode joins, coordinate completeness, and output hashes can be independently recomputed.",PENDING,TECHNICAL_ONLY,"technical integrity cannot elevate biological claims"
```

