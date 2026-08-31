process BNS019_RECEIPT {
    tag "$meta.id"
    label 'process_single'

    conda "conda-forge::python=3.11"

    input:
    tuple val(meta), path(samplesheet), path(versions), path(outputs)
    path receipt_generator_script

    output:
    tuple val(meta), path("*.bionexus_receipt.json"), emit: receipt
    tuple val(meta), path("*.bionexus_card.json"), emit: card, optional: true
    path "versions.yml", emit: versions

    when:
    task.ext.when == null || task.ext.when

    script:
    def prefix = task.ext.prefix ?: "${meta.id}"
    def pipeline_name = task.ext.pipeline_name ?: "nf-core/pipeline"
    """
    python ${receipt_generator_script} \
        --pipeline-name "${pipeline_name}" \
        --samplesheet ${samplesheet} \
        --versions ${versions} \
        --outputs ${outputs} \
        --output ${prefix}.bionexus_receipt.json \
        --card-output ${prefix}.bionexus_card.json

    cat <<-END_VERSIONS > versions.yml
    "${task.process}":
        python: $(python --version | sed 's/Python //g')
        bionexus_receipt_schema: "bionexus.tool-execution-receipt.v1"
    END_VERSIONS
    """
}
