nextflow.enable.dsl = 2

include { BNS019_SEMCONV } from './modules/local/bns019_semconv/main'

params.record = null
params.semantics = null
params.standard_root = null
params.outdir = 'results'

workflow {
    if (!params.record || !params.semantics || !params.standard_root) {
        error "--record, --semantics, and --standard_root are required"
    }

    records = Channel.of([
        [id: 'trial-record'],
        file(params.record, checkIfExists: true),
        file(params.semantics, checkIfExists: true)
    ])
    standard_release = file(params.standard_root, checkIfExists: true)
    adapter_script = file("${projectDir}/bin/bns019_nfcore_adapter.py", checkIfExists: true)
    validator_script = file("${projectDir}/../python/bns019_validator.py", checkIfExists: true)

    BNS019_SEMCONV(records, standard_release, adapter_script, validator_script)
}

workflow.onComplete {
    log.info "BNS-019 interoperability adapter completed: ${workflow.success}"
}
