#!/usr/bin/env Rscript

# Attach a verified BNS-019 envelope to Seurat object@misc. The adapter does
# not modify assays, reductions, metadata columns, identities, or cell labels.

script_args <- commandArgs(trailingOnly = FALSE)
file_arg <- grep("^--file=", script_args, value = TRUE)
script_path <- if (length(file_arg)) sub("^--file=", "", file_arg[[1]]) else "interoperability/bns019/seurat/bns019_seurat_adapter.R"
validator_path <- file.path(dirname(dirname(normalizePath(script_path, winslash = "/", mustWork = TRUE))), "r", "bns019_validator.R")
source(validator_path, local = TRUE)

HOST_KEY <- "bionexus"
ENVELOPE_KEY <- "scientific_semantic_envelope_json"
RELEASE_DIGEST_KEY <- "bns019_release_digest_sha256"

canonical_json <- function(value) {
  as.character(jsonlite::toJSON(
    canonicalize_json(value),
    auto_unbox = TRUE,
    null = "null",
    na = "null",
    digits = NA,
    pretty = FALSE
  ))
}

build_envelope <- function(registry, convention, attributes, producer, record_id, source_record_sha256) {
  report <- validate_attributes(registry, convention, attributes)
  if (!isTRUE(report$valid)) stop(paste(report$errors, collapse = "; "), call. = FALSE)
  payload <- list(
    schema_url = registry$schema_url,
    convention = convention,
    producer = producer,
    record_id = record_id,
    source_record_sha256 = source_record_sha256,
    attributes = report$normalized_attributes
  )
  payload$semantic_fingerprint_sha256 <- sha256_text(canonical_json(payload))
  payload
}

attach_semantics <- function(object, standard_root, convention, attributes, producer,
                             record_id = NULL, source_record_sha256 = NULL) {
  if (!inherits(object, "Seurat")) stop("input must inherit from Seurat", call. = FALSE)
  release <- load_verified_release(standard_root)
  envelope <- build_envelope(
    release$registry,
    convention,
    attributes,
    producer,
    record_id,
    source_record_sha256
  )
  namespace <- object@misc[[HOST_KEY]]
  if (is.null(namespace)) namespace <- list()
  if (!is.list(namespace)) stop("object@misc$bionexus already exists and is not a list", call. = FALSE)
  namespace[[RELEASE_DIGEST_KEY]] <- release$manifest$release_digest_sha256
  namespace[[ENVELOPE_KEY]] <- canonical_json(envelope)
  object@misc[[HOST_KEY]] <- namespace
  list(object = object, envelope = envelope, manifest = release$manifest)
}

parse_adapter_args <- function(args) {
  output <- list(
    input = NULL,
    output = NULL,
    standard_root = NULL,
    semantics = NULL,
    producer = "bns019.interop.seurat",
    record_id = NULL,
    result = NULL
  )
  allowed <- names(output)
  index <- 1L
  while (index <= length(args)) {
    key <- sub("^--", "", args[[index]])
    key <- gsub("-", "_", key, fixed = TRUE)
    if (!(key %in% allowed) || index == length(args)) stop(sprintf("unknown or incomplete argument: %s", args[[index]]), call. = FALSE)
    output[[key]] <- args[[index + 1L]]
    index <- index + 2L
  }
  for (required in c("input", "output", "standard_root", "semantics")) {
    if (is.null(output[[required]])) stop(sprintf("--%s is required", gsub("_", "-", required)), call. = FALSE)
  }
  output
}

main_adapter <- function() {
  if (!requireNamespace("SeuratObject", quietly = TRUE)) stop("SeuratObject is required", call. = FALSE)
  args <- parse_adapter_args(commandArgs(trailingOnly = TRUE))
  semantic_input <- read_object(args$semantics, "semantic input")
  source_sha256 <- sha256_file(args$input)
  object <- readRDS(args$input)
  dimensions_before <- dim(object)
  attached <- attach_semantics(
    object,
    args$standard_root,
    semantic_input$convention,
    semantic_input$attributes,
    args$producer,
    args$record_id,
    source_sha256
  )
  if (!identical(dimensions_before, dim(attached$object))) stop("adapter changed Seurat dimensions", call. = FALSE)
  saveRDS(attached$object, args$output, version = 3)
  round_trip <- readRDS(args$output)
  stored <- round_trip@misc[[HOST_KEY]]
  stored_envelope <- jsonlite::fromJSON(stored[[ENVELOPE_KEY]], simplifyVector = FALSE)
  if (!json_equal(stored_envelope, attached$envelope)) stop("Seurat round trip changed the semantic envelope", call. = FALSE)

  result <- list(
    schema = "urn:bionexus:bns019-host-adapter-result:1",
    implementation = list(id = "bns019-seurat-adapter", track = "host_adapter", host = "seurat"),
    standard = list(
      id = "BNS-019",
      version = attached$manifest$version,
      release_digest_sha256 = stored[[RELEASE_DIGEST_KEY]]
    ),
    status = "PASS",
    checks = list(
      registry_verified = TRUE,
      misc_only_contract = TRUE,
      dimensions_preserved = TRUE,
      rds_round_trip = TRUE,
      fingerprint_preserved = TRUE
    ),
    claim_boundary = "Metadata interoperability only; no Seurat analysis or biological result was validated."
  )
  payload <- jsonlite::toJSON(result, auto_unbox = TRUE, null = "null", digits = NA, pretty = TRUE)
  if (is.null(args$result)) cat(payload, "\n", sep = "") else writeLines(enc2utf8(payload), args$result, useBytes = TRUE)
  0L
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main_adapter(), error = function(e) {
    message("ERROR: ", e$message)
    2L
  })
  quit(save = "no", status = status, runLast = FALSE)
}
