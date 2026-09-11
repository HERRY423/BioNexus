"""Frozen, local computational evidence; never an independent certification."""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from scipy import sparse, stats

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
DATA = REPO / 'data/flagship/kang2018_pbmc_ifnb/pbmc_ifnb_counts.h5ad'
PARSE = REPO / 'data/independent/parse10m_pbmc_ifnb_natural_v1/parse_ifnb_pbs_pseudobulk.h5ad'
EXTRACTION = PARSE.with_name('EXTRACTION_MANIFEST.json')


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''):
            h.update(block)
    return h.hexdigest()


def json_default(x):
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    if hasattr(x, 'value'):
        return x.value
    return str(x)


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=json_default, allow_nan=False) + '\n', encoding='utf-8')


def bh(p):
    p = np.asarray(p, float)
    out = np.full_like(p, np.nan)
    ok = np.isfinite(p)
    q = p[ok]
    if len(q):
        order = np.argsort(q, kind='stable')
        adjusted = np.minimum.accumulate((q[order] * len(q) / np.arange(1, len(q) + 1))[::-1])[::-1]
        target = np.empty_like(q)
        target[order] = np.minimum(adjusted, 1)
        out[ok] = target
    return out


def freeze():
    if (HERE / 'FREEZE.json').exists():
        raise FileExistsError('Freeze exists; do not silently change a registered local analysis.')
    snapshot = HERE / 'frozen-source'
    snapshot.mkdir(exist_ok=False)
    source_hashes = {}
    for p in sorted((REPO / 'src/bionexus').rglob('*')):
        if p.is_file() and p.suffix in {'.py', '.json'}:
            rel = p.relative_to(REPO / 'src')
            dest = snapshot / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(p, dest)
            source_hashes[rel.as_posix()] = digest(dest)
    wrapper = REPO / 'skills/single-cell-rna-qc/scripts/scrna_deseq.py'
    shutil.copyfile(wrapper, snapshot / 'scrna_deseq.py')
    source_hashes['scrna_deseq.py'] = digest(snapshot / 'scrna_deseq.py')
    payload = {
        'study_id': 'BN-METHODS-20260908', 'created_utc': datetime.now(timezone.utc).isoformat(),
        'registration': 'LOCAL_PREEXECUTION_FREEZE_NOT_EXTERNAL_PREREGISTRATION',
        'git_head': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=REPO, text=True).strip(),
        'git_status': subprocess.check_output(['git', 'status', '--short'], cwd=REPO, text=True),
        'source_hashes': source_hashes,
        'input_hashes': {p.relative_to(REPO).as_posix(): digest(p) for p in [DATA, PARSE, EXTRACTION]},
        'protocol_sha256': digest(HERE / 'PROTOCOL.md'), 'runner_sha256': digest(__file__),
        'python': sys.version, 'platform': platform.platform(),
        'packages': {k: importlib.metadata.version(k) for k in ['numpy', 'pandas', 'scipy', 'anndata', 'pydeseq2', 'matplotlib']},
        'api_credentials_present': {k: bool(os.environ.get(k)) for k in ['OPENAI_API_KEY', 'ANTHROPIC_API_KEY', 'GEMINI_API_KEY']},
        'seed_base': 260908, 'product_edits_during_experiment': False,
    }
    write_json(HERE / 'FREEZE.json', payload)
    print('Freeze written', digest(HERE / 'FREEZE.json'), flush=True)


def verify_freeze():
    frozen = json.loads((HERE / 'FREEZE.json').read_text(encoding='utf-8'))
    if digest(__file__) != frozen['runner_sha256'] or digest(HERE / 'PROTOCOL.md') != frozen['protocol_sha256']:
        raise ValueError('Protocol/runner changed after freeze')
    for rel, h in frozen['source_hashes'].items():
        if digest(HERE / 'frozen-source' / rel) != h:
            raise ValueError(f'Frozen source changed: {rel}')
    for rel, h in frozen['input_hashes'].items():
        if digest(REPO / rel) != h:
            raise ValueError(f'Data changed: {rel}')
    sys.path.insert(0, str(HERE / 'frozen-source'))
    return frozen


def simulate(out):
    records = []
    per_gene = out / 'gene-outcomes.csv.gz'
    import gzip
    with gzip.open(per_gene, 'wt', encoding='utf-8', newline='') as stream:
        first = True
        grid = list(itertools.product([4, 8], [20, 100], [0., .8], [0., .2]))
        for grid_id, (donors, cells, heterogeneity, nonnull) in enumerate(grid):
            for rep in range(50):
                seed = 260908 + grid_id * 1000 + rep
                rng = np.random.default_rng(seed)
                genes = 200
                truth = np.zeros(genes, bool)
                effect = np.zeros(genes)
                n_signal = int(genes * nonnull)
                truth[:n_signal] = True
                effect[:n_signal] = np.where(np.arange(n_signal) % 2 == 0, np.log(2), -np.log(2))
                baseline = rng.lognormal(1.5, .6, genes)
                donor_shift = rng.normal(0, heterogeneity, (2 * donors, genes))
                condition = np.repeat([0, 1], donors)
                mean = baseline[None, :] * np.exp(donor_shift + condition[:, None] * effect)
                values = rng.negative_binomial(1 / .3, 1 / (1 + .3 * mean[:, None, :]), size=(2 * donors, cells, genes))
                log = np.log1p(values)
                start = time.perf_counter()
                cell_p = stats.ttest_ind(log[:donors].reshape(-1, genes), log[donors:].reshape(-1, genes), equal_var=False, axis=0).pvalue
                donor_p = stats.ttest_ind(log[:donors].mean(axis=1), log[donors:].mean(axis=1), equal_var=False, axis=0).pvalue
                elapsed = time.perf_counter() - start
                for method, p in [('cell_welch', cell_p), ('donor_mean_welch', donor_p)]:
                    q = bh(p)
                    hit = q < .05
                    tp = int((hit & truth).sum())
                    fp = int((hit & ~truth).sum())
                    records.append(dict(seed=seed, grid_id=grid_id, donors_per_group=donors, cells_per_donor=cells,
                                        donor_sd=heterogeneity, nonnull_fraction=nonnull, method=method,
                                        discoveries=int(hit.sum()), true_positive=tp, false_positive=fp,
                                        fdp=fp / max(int(hit.sum()), 1), sensitivity=tp / n_signal if n_signal else None,
                                        any_false_positive=int(fp > 0), pvalue_nonfinite=int((~np.isfinite(p)).sum()),
                                        two_methods_seconds=elapsed))
                    frame = pd.DataFrame({'seed': seed, 'method': method, 'gene': np.arange(genes), 'true_nonnull': truth,
                                          'true_log_effect': effect, 'pvalue': p, 'padj': q})
                    frame.to_csv(stream, index=False, header=first)
                    first = False
            print(f'E1 factorial stratum {grid_id + 1}/{len(grid)} complete', flush=True)
    frame = pd.DataFrame(records)
    frame.to_csv(out / 'dataset-outcomes.csv', index=False)
    summaries = []
    rng = np.random.default_rng(99887)
    keys = ['grid_id', 'donors_per_group', 'cells_per_donor', 'donor_sd', 'nonnull_fraction', 'method']
    for key, group in frame.groupby(keys):
        row = dict(zip(keys, key))
        row['n_datasets'] = len(group)
        for metric in ['fdp', 'sensitivity', 'any_false_positive']:
            x = group[metric].dropna().to_numpy()
            if len(x):
                means = rng.choice(x, size=(2000, len(x)), replace=True).mean(axis=1)
                row.update({metric: float(x.mean()), metric + '_lo': float(np.quantile(means, .025)), metric + '_hi': float(np.quantile(means, .975))})
        summaries.append(row)
    pd.DataFrame(summaries).to_csv(out / 'summary.csv', index=False)
    write_json(out / 'status.json', {'status': 'COMPLETE', 'datasets': 800, 'method_results': len(records),
                                    'truth': 'SYNTHETIC_GENERATING_MECHANISM', 'independent_validation': False})


def dense(x):
    return x.toarray() if sparse.issparse(x) else np.asarray(x)


def real_null(out):
    import anndata as ad
    a = ad.read_h5ad(DATA)
    mask = (a.obs['condition'].astype(str) == 'ctrl') & (a.obs['geo_cell_type'].astype(str) == 'CD14+ Monocytes')
    a = a[mask].copy()
    total = np.asarray(a.X.sum(axis=0)).ravel()
    select = np.argsort(-total, kind='stable')[total[np.argsort(-total, kind='stable')] >= 10][:1000]
    genes = a.var_names[select].astype(str)
    library = np.asarray(a.X.sum(axis=1)).ravel()
    if (library <= 0).any():
        raise ValueError('Zero-library cell in real null input')
    x = np.log1p(dense(a.X[:, select]) / library[:, None] * 10000)
    donors = sorted(a.obs.donor.astype(str).unique())
    donor_cells = [np.flatnonzero(a.obs.donor.astype(str).to_numpy() == d) for d in donors]
    means = np.stack([x[idx].mean(axis=0) for idx in donor_cells])
    combos = [c for c in itertools.combinations(range(8), 4) if 0 in c]
    differences = []
    for c in combos:
        other = sorted(set(range(8)) - set(c))
        differences.append(means[list(c)].mean(axis=0) - means[other].mean(axis=0))
    differences = np.array(differences)
    rows, gene_rows = [], []
    for i, c in enumerate(combos):
        other = sorted(set(range(8)) - set(c))
        left = np.concatenate([donor_cells[j] for j in c])
        right = np.concatenate([donor_cells[j] for j in other])
        methods = {
            'cell_welch': stats.ttest_ind(x[left], x[right], equal_var=False, axis=0).pvalue,
            'donor_mean_welch': stats.ttest_ind(means[list(c)], means[other], equal_var=False, axis=0).pvalue,
            'exact_donor_randomization': (np.abs(differences) >= np.abs(differences[i]) - 1e-12).mean(axis=0),
        }
        for method, p in methods.items():
            q = bh(p)
            rows.append(dict(partition=i, method=method, donors_A='|'.join(donors[j] for j in c),
                             donors_B='|'.join(donors[j] for j in other), n_genes=len(genes), discoveries=int((q < .05).sum()),
                             pvalue_nonfinite=int((~np.isfinite(p)).sum())))
            gene_rows.append(pd.DataFrame({'partition': i, 'method': method, 'gene': genes, 'pvalue': p, 'padj': q}))
    pd.DataFrame(rows).to_csv(out / 'partition-outcomes.csv', index=False)
    pd.concat(gene_rows).to_csv(out / 'gene-outcomes.csv.gz', index=False)
    pd.DataFrame(means, index=donors, columns=genes).to_csv(out / 'donor-logmeans.csv')
    summary = []
    for method, group in pd.DataFrame(rows).groupby('method'):
        summary.append(dict(method=method, n_partitions=len(group), partitions_with_discoveries=int((group.discoveries > 0).sum()),
                            conditional_any_discovery_fraction=float((group.discoveries > 0).mean()),
                            median_discoveries=float(group.discoveries.median()), max_discoveries=int(group.discoveries.max())))
    write_json(out / 'summary.json', {'status': 'COMPLETE', 'n_control_monocytes': a.n_obs, 'n_donors': len(donors),
                                     'donor_cell_counts': dict(zip(donors, map(len, donor_cells))), 'n_genes': len(genes),
                                     'partition_results': summary, 'independent_partitions': False,
                                     'minimum_exact_two_sided_p': 1 / len(combos)})


def prepare_pseudobulk():
    import anndata as ad
    a = ad.read_h5ad(DATA)
    rows, meta = [], []
    for (donor, condition), indices in a.obs.groupby(['donor', 'condition'], observed=True).indices.items():
        sid = f'{donor}__{condition}'
        rows.append(np.asarray(a.X[indices].sum(axis=0)).ravel())
        meta.append(dict(sample_id=sid, donor=str(donor), condition='control' if condition == 'ctrl' else 'treated', n_cells=len(indices)))
    md = pd.DataFrame(meta).set_index('sample_id')
    kang = pd.DataFrame(rows, index=md.index, columns=a.var_names.astype(str))
    b = ad.read_h5ad(PARSE)
    pm = b.obs.copy()
    pm['donor'] = pm['donor'].astype(str)
    pm['condition'] = pm['cytokine'].astype(str).map({'PBS': 'control', 'IFN-beta': 'treated'})
    if pm.condition.isna().any():
        raise ValueError('Unexpected Parse condition')
    parse = pd.DataFrame(dense(b.X), index=pm.index, columns=b.var_names.astype(str))
    extraction = json.loads(EXTRACTION.read_text(encoding='utf-8'))
    if digest(PARSE) != extraction['output_sha256']:
        raise ValueError('Parse extraction hash mismatch')
    for c, m in [(kang, md), (parse, pm)]:
        values = c.to_numpy()
        if c.columns.duplicated().any() or not np.isfinite(values).all() or (values < 0).any() or not np.equal(values, np.floor(values)).all():
            raise ValueError('Invalid raw count input')
        if not (m.groupby('donor').condition.nunique() == 2).all():
            raise ValueError('Donor not fully paired')
    common = sorted(set(kang.columns[(kang >= 10).sum(axis=0) >= 4]) & set(parse.columns[(parse >= 10).sum(axis=0) >= 4]))
    score = (kang.div(kang.sum(axis=1), axis=0)[common].mean(axis=0) + parse.div(parse.sum(axis=1), axis=0)[common].mean(axis=0)) / 2
    selected = score.sort_values(ascending=False, kind='stable').head(2000).index
    return {'kang': (kang[selected].astype(int), md), 'parse': (parse[selected].astype(int), pm)}, extraction


def paired_models(out):
    from pydeseq2.dds import DeseqDataSet
    from pydeseq2.ds import DeseqStats
    cohorts, extraction = prepare_pseudobulk()
    tables, fits = {}, []
    for cohort, (counts, metadata) in cohorts.items():
        counts.to_csv(out / f'{cohort}-counts.csv')
        metadata.to_csv(out / f'{cohort}-metadata.csv')
        for model, formula in [('unpaired', '~ condition'), ('paired', '~ donor + condition')]:
            start = time.perf_counter()
            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter('always')
                dds = DeseqDataSet(counts=counts, metadata=metadata, design=formula, refit_cooks=True, n_cpus=2, quiet=True)
                dds.deseq2()
                ds = DeseqStats(dds, contrast=['condition', 'treated', 'control'], alpha=.05, n_cpus=2, quiet=True)
                ds.summary()
            table = ds.results_df.copy()
            table.index.name = 'gene'
            table.rename(columns={'padj': 'padj_native'}, inplace=True)
            table['padj'] = bh(table.pvalue.to_numpy())
            path = out / f'{cohort}-{model}-de.csv'
            table.to_csv(path)
            matrix = pd.DataFrame(dds.obsm['design_matrix'], index=counts.index)
            matrix_path = out / f'{cohort}-{model}-design.csv'
            matrix.to_csv(matrix_path)
            rank = int(np.linalg.matrix_rank(matrix.to_numpy()))
            receipt = dict(cohort=cohort, model=model, method='pydeseq2', design=formula,
                           statistical_unit='donor', aggregation='donor_pseudobulk', fit_status='COMPLETE',
                           result_sha256=digest(path), counts_sha256=digest(out / f'{cohort}-counts.csv'),
                           sample_metadata_sha256=digest(out / f'{cohort}-metadata.csv'),
                           design_matrix_sha256=digest(matrix_path), design_rank=rank, residual_df=len(counts) - rank,
                           design_matrix_columns=list(matrix.columns), n_samples=len(counts), n_donors=metadata.donor.nunique(),
                           n_genes=len(table), significant=int((table.padj < .05).sum()), native_significant=int((table.padj_native < .05).sum()),
                           n_nonfinite_p=int((~np.isfinite(table.pvalue)).sum()), seconds=time.perf_counter() - start,
                           warnings=sorted({f'{w.category.__name__}: {w.message}' for w in caught}),
                           scientific_authority='LOCAL_EXECUTION_NOT_EXTERNAL_ATTESTATION', fdr_method='BH_on_all_finite_raw_pvalues')
            write_json(out / f'{cohort}-{model}-receipt.json', receipt)
            tables[(cohort, model)] = table
            fits.append(receipt)
            print(f'E2 fit {cohort}/{model}: {len(table)} genes; {receipt["seconds"]:.1f}s', flush=True)
    comparisons = []
    for cohort in cohorts:
        u, p = tables[(cohort, 'unpaired')], tables[(cohort, 'paired')]
        us, ps = set(u.index[u.padj < .05]), set(p.index[p.padj < .05])
        comparisons.append(dict(cohort=cohort, significant_unpaired=len(us), significant_paired=len(ps),
                                gained_with_pairing=len(ps - us), lost_with_pairing=len(us - ps),
                                significant_jaccard=len(us & ps) / len(us | ps) if us | ps else None,
                                all_gene_effect_spearman=float(stats.spearmanr(u.log2FoldChange, p.log2FoldChange, nan_policy='omit').statistic),
                                sign_changes=int((np.sign(u.log2FoldChange) != np.sign(p.log2FoldChange)).sum())))
    discovery = tables[('kang', 'paired')].dropna(subset=['pvalue', 'log2FoldChange']).sort_values('pvalue', kind='stable').head(100)
    validation = tables[('parse', 'paired')].loc[discovery.index]
    signature = pd.DataFrame({'gene': discovery.index, 'kang_log2fc': discovery.log2FoldChange.to_numpy(),
                              'parse_log2fc': validation.log2FoldChange.to_numpy(), 'kang_pvalue': discovery.pvalue.to_numpy(),
                              'parse_pvalue': validation.pvalue.to_numpy()})
    signature.to_csv(out / 'cross-cohort-signature.csv', index=False)
    counts, metadata = cohorts['parse']
    logcpm = np.log2(counts.div(counts.sum(axis=1), axis=0) * 1e6 + 1)
    donor_scores = []
    for donor, group in metadata.groupby('donor', observed=True):
        treated = group.index[group.condition == 'treated'][0]
        control = group.index[group.condition == 'control'][0]
        change = logcpm.loc[treated, discovery.index] - logcpm.loc[control, discovery.index]
        donor_scores.append(dict(donor=donor, score=float((change.to_numpy() * np.sign(discovery.log2FoldChange.to_numpy())).mean())))
    pd.DataFrame(donor_scores).to_csv(out / 'parse-donor-signature-scores.csv', index=False)
    values = np.array([r['score'] for r in donor_scores])
    flips = np.array(list(itertools.product([-1, 1], repeat=len(values))))
    observed = abs(values.mean())
    empirical_p = float((np.abs((flips * values).mean(axis=1)) >= observed - 1e-12).mean())
    write_json(out / 'summary.json', dict(status='COMPLETE', fits=fits, model_comparisons=comparisons,
                                         cross_cohort=dict(n_signature=len(discovery), direction_concordance=float((np.sign(discovery.log2FoldChange.to_numpy()) == np.sign(validation.log2FoldChange.to_numpy())).mean()),
                                                           exact_donor_signflip_p=empirical_p, n_donors=len(values), n_assignments=len(flips),
                                                           interpretation='Exploratory cross-cohort direction consistency; not independent blinded validation'),
                                         parse_source_gate=extraction['data_gate_status'], parse_source_mismatched_cells=extraction['per_cell_expression_record_mismatches'],
                                         scope='2000 prespecified common abundant genes; mixed PBMC cell composition unresolved'))


def challenge_cases(real):
    table_path = real / 'kang-paired-de.csv'
    table = pd.read_csv(table_path)
    meta = pd.read_csv(real / 'kang-metadata.csv', dtype={'donor': str})
    receipt = json.loads((real / 'kang-paired-receipt.json').read_text(encoding='utf-8'))
    positive = table.loc[(table.padj < .05) & (table.log2FoldChange > 0)].sort_values('pvalue')
    negative = table.loc[(table.padj > .5) & (table.pvalue > .1)].sort_values('gene')
    if positive.empty or negative.empty:
        raise ValueError('Prerequired positive or negative case unavailable; do not substitute')
    pos, neg = str(positive.iloc[0].gene), str(negative.iloc[0].gene)
    absent = 'BN_NOT_IN_INPUT_20260908'
    if absent in set(table.gene):
        raise ValueError('Absent gene collision')
    families = [
        ('valid_positive', False, f'{pos} is upregulated and significant after FDR correction in the supplied treated-versus-control result.'),
        ('valid_negative', False, f'{neg} was not significant after FDR correction in the supplied result.'),
        ('valid_limited', False, 'These differential-expression results do not establish causality or clinical efficacy.'),
        ('valid_table_presence', False, f'The supplied differential-expression table contains a result for {pos}.'),
        ('absent_gene', True, f'{absent} is significantly upregulated after FDR correction in the supplied result.'),
        ('wrong_direction', True, f'{pos} is significantly downregulated after FDR correction in the supplied treated-versus-control result.'),
        ('false_significance', True, f'{neg} is significant after FDR correction in the supplied result.'),
        ('false_negative', True, f'{pos} was not significant after FDR correction in the supplied result.'),
        ('false_global_null', True, 'No genes were significant after FDR correction in the supplied result.'),
        ('causal_overclaim', True, f'These observational results prove that {pos} causes disease.'),
        ('clinical_overclaim', True, f'{pos} is a clinically validated diagnostic biomarker with proven clinical efficacy.'),
        ('missing_fdr', True, f'{pos} is significant after FDR correction in the supplied result.'),
        ('invalid_probability', True, f'{pos} is significant after FDR correction in the supplied result.'),
        ('missing_receipt', True, 'The supplied execution evidence verifies a completed donor-level fit for this table.'),
        ('wrong_result_hash', True, 'The supplied execution receipt is bound to the exact supplied result table.'),
        ('changed_result', True, 'The supplied result table is unchanged from the recorded execution output.'),
        ('failed_fit', True, 'The recorded model fit completed successfully.'),
        ('wrong_design', True, 'The recorded donor-adjusted model formula agrees with the fitted design matrix.'),
    ]
    cases = []
    for family, invalid, text in families:
        for phrasing in range(3):
            claim = [text, 'For this completed analysis, ' + text[0].lower() + text[1:], 'Our reported conclusion is: ' + text][phrasing]
            t, m, r = table.copy(), meta.copy(), copy.deepcopy(receipt)
            if family == 'missing_fdr':
                t = t.drop(columns=['padj', 'padj_native'])
            if family == 'invalid_probability':
                t.loc[0, 'padj'] = 1.2
            if family == 'missing_receipt':
                r = None
            if family == 'wrong_result_hash':
                r['result_sha256'] = '0' * 64
            if family == 'changed_result':
                t.loc[t.gene == pos, 'log2FoldChange'] *= -1
            if family == 'failed_fit':
                r['fit_status'] = 'FAILED'
            if family == 'wrong_design':
                r['design'] = '~ condition'
            cases.append(dict(case_id=f'{family}-{phrasing}', family=family, paraphrase=phrasing, invalid=invalid,
                              claim=claim, table=t, metadata=m, receipt=r,
                              oracle='Developer-authored table/receipt consistency or claim-boundary label; not independent human judgment'))
    return cases


def audit_challenge(out, real):
    from bionexus.de_audit import audit_differential_expression
    cases = challenge_cases(real)
    case_root = out / 'cases'
    case_root.mkdir()
    rows, definitions = [], []
    for case in cases:
        folder = case_root / case['case_id']
        folder.mkdir()
        original = real / 'kang-paired-de.csv'
        table_path = folder / 'de.csv'
        if case['family'] not in {'missing_fdr', 'invalid_probability', 'changed_result'}:
            shutil.copyfile(original, table_path)
        else:
            case['table'].to_csv(table_path, index=False)
        shutil.copyfile(real / 'kang-metadata.csv', folder / 'metadata.csv')
        shutil.copyfile(real / 'kang-paired-design.csv', folder / 'design.csv')
        write_json(folder / 'receipt.json', case['receipt'])
        definition = {k: v for k, v in case.items() if k not in {'table', 'metadata', 'receipt'}}
        definition['result_sha256'] = digest(table_path)
        definition['receipt_result_sha256'] = case['receipt'].get('result_sha256') if case['receipt'] else None
        write_json(folder / 'case.json', definition)
        definitions.append(definition)
        for arm in ['accept_all', 'reject_all', 'deterministic_checklist', 'bionexus_full', 'without_claim_text', 'without_execution_metadata']:
            start = time.perf_counter()
            output = None
            if arm in {'accept_all', 'reject_all'}:
                status = 'ACCEPT' if arm == 'accept_all' else 'REJECT'
                issue, abstain = arm == 'reject_all', False
                accepted = arm == 'accept_all'
            elif arm == 'deterministic_checklist':
                t, m, r = case['table'], case['metadata'], case['receipt']
                valid_prob = 'padj' in t and t['padj'].dropna().between(0, 1).all()
                donors_ok = m.groupby('condition').donor.nunique().min() >= 3
                donor_record = bool(r and r.get('statistical_unit') == 'donor')
                accepted = bool(valid_prob and donors_ok and donor_record)
                status, issue, abstain = ('ACCEPT', False, False) if accepted else ('REJECT', True, False)
            else:
                result = audit_differential_expression(
                    de_table=table_path, sample_metadata=case['metadata'],
                    execution_record=None if arm == 'without_execution_metadata' else case['receipt'],
                    claim_text=None if arm == 'without_claim_text' else case['claim'], donor_col='donor', condition_col='condition')
                output = result.to_dict()
                write_json(folder / f'{arm}.json', output)
                status, accepted = result.overall_status, result.passed
                issue = any(f.severity.value in {'BLOCKER', 'HIGH_IMPACT'} for f in result.findings)
                abstain = status in {'NEEDS_DATA', 'NOT_ASSESSED'}
            rows.append(dict(case_id=case['case_id'], family=case['family'], paraphrase=case['paraphrase'], invalid=case['invalid'],
                             arm=arm, status=status, accepted=bool(accepted), issue_identified=bool(issue), abstained=bool(abstain),
                             seconds=time.perf_counter() - start))
    write_json(out / 'case-definitions.json', definitions)
    frame = pd.DataFrame(rows)
    frame.to_csv(out / 'case-outcomes.csv', index=False)
    summary = []
    for arm, group in frame.groupby('arm'):
        invalid, valid = group[group.invalid], group[~group.invalid]
        summary.append(dict(arm=arm, invalid_cases=len(invalid), valid_cases=len(valid),
                            invalid_accepted=int(invalid.accepted.sum()), valid_retained=int(valid.accepted.sum()),
                            invalid_issue_identified=int(invalid.issue_identified.sum()), invalid_abstained=int(invalid.abstained.sum()),
                            unsupported_acceptance_rate=float(invalid.accepted.mean()), valid_retention=float(valid.accepted.mean()),
                            median_machine_seconds=float(group.seconds.median())))
    write_json(out / 'summary.json', {'status': 'COMPLETE', 'n_cases': len(cases), 'n_families': len(set(frame.family)),
                                     'independent_expert_labels': False, 'live_llm_baselines': 'NOT_RUN_NO_API_CREDENTIALS',
                                     'human_review_minutes': None, 'arms': summary,
                                     'warning': 'Issue identification is any high-impact finding, not necessarily correct localization. See raw findings.'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['freeze', 'simulate', 'real-null', 'paired', 'challenge'])
    parser.add_argument('--run-id', default='run-01')
    parser.add_argument('--real-run-id', default='run-01')
    args = parser.parse_args()
    if args.stage == 'freeze':
        freeze()
        return
    verify_freeze()
    out = HERE / args.run_id / args.stage
    out.mkdir(parents=True, exist_ok=False)
    write_json(out / 'execution-start.json', {'started_utc': datetime.now(timezone.utc).isoformat(), 'freeze_sha256': digest(HERE / 'FREEZE.json'), 'stage': args.stage})
    start = time.perf_counter()
    try:
        if args.stage == 'simulate':
            simulate(out)
        elif args.stage == 'real-null':
            real_null(out)
        elif args.stage == 'paired':
            paired_models(out)
        else:
            audit_challenge(out, HERE / args.real_run_id / 'paired')
        write_json(out / 'execution-end.json', {'status': 'COMPLETE', 'seconds': time.perf_counter() - start,
                                              'ended_utc': datetime.now(timezone.utc).isoformat()})
    except Exception as exc:
        write_json(out / 'FAILURE.json', {'status': 'FAILED', 'error': str(exc), 'traceback': traceback.format_exc(), 'seconds': time.perf_counter() - start})
        raise


if __name__ == '__main__':
    main()
