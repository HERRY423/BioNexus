process BNS019_SEMCONV {
    // Historical standalone trial fixture, not a reusable nf-core module.
    tag "$meta.id"

    conda "conda-forge::python=3.11"

    input:
    tuple val(meta), path(record), path(semantics)
    path standard_release
    path adapter_script
    path validator_script

    output:
    tuple val(meta), path("*.bns019.json"), emit: record
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = task.ext.prefix ?: "${meta.id}"
    """
    python ${adapter_script} \\
        --validator ${validator_script} \\
        --standard-root ${standard_release} \\
        --record ${record} \\
        --semantics ${semantics} \\
        --output ${prefix}.bns019.json \\
        --versions versions.yml
    """
}
