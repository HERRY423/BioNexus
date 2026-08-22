#!/usr/bin/env Rscript

# Independent BNS-019 producer validator. This file does not call Python or
# import the BioNexus package; it consumes the same language-neutral release.

if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("jsonlite is required", call. = FALSE)
}
if (!requireNamespace("digest", quietly = TRUE)) {
  stop("digest is required for SHA-256 release verification", call. = FALSE)
}

MANIFEST_SCHEMA <- "urn:bionexus:scientific-semantic-release-manifest:1"
RESULT_SCHEMA <- "urn:bionexus:bns019-implementation-result:1"
STANDARD_ID <- "BNS-019"
ARTIFACT_NAME <- "bionexus-scientific-semantic-conventions"

read_object <- function(path, label) {
  value <- tryCatch(
    jsonlite::fromJSON(path, simplifyVector = FALSE),
    error = function(e) stop(sprintf("cannot read %s: %s", label, e$message), call. = FALSE)
  )
  if (!is.list(value) || is.null(names(value))) {
    stop(sprintf("%s must be a JSON object", label), call. = FALSE)
  }
  value
}

sha256_file <- function(path) {
  digest::digest(file = path, algo = "sha256", serialize = FALSE)
}

sha256_text <- function(value) {
  digest::digest(enc2utf8(value), algo = "sha256", serialize = FALSE)
}

canonical_records_json <- function(records) {
  ordered <- lapply(records, function(record) {
    list(path = record$path, sha256 = record$sha256, size_bytes = record$size_bytes)
  })
  as.character(jsonlite::toJSON(
    ordered,
    auto_unbox = TRUE,
    null = "null",
    na = "null",
    digits = NA,
    pretty = FALSE
  ))
}

safe_relative_path <- function(path) {
  if (!is.character(path) || length(path) != 1L || !nzchar(path) ||
      grepl("^(/|[A-Za-z]:)", path) ||
      any(strsplit(gsub("\\\\", "/", path), "/", fixed = TRUE)[[1]] %in% c(".", ".."))) {
    stop(sprintf("unsafe manifest path: %s", path), call. = FALSE)
  }
  path
}

load_verified_release <- function(root) {
  root <- normalizePath(root, winslash = "/", mustWork = TRUE)
  manifest <- read_object(file.path(root, "release-manifest.json"), "release manifest")
  if (!identical(manifest$schema, MANIFEST_SCHEMA)) stop("unsupported release manifest schema", call. = FALSE)
  if (!identical(manifest$standard_id, STANDARD_ID) || !identical(manifest$artifact_name, ARTIFACT_NAME)) {
    stop("release identity mismatch", call. = FALSE)
  }
  version <- trimws(paste(readLines(file.path(root, "VERSION"), warn = FALSE, encoding = "UTF-8"), collapse = "\n"))
  if (!nzchar(version) || !identical(manifest$version, version)) stop("release version mismatch", call. = FALSE)
  records <- manifest$files
  if (!is.list(records) || length(records) == 0L) stop("manifest files must be a non-empty array", call. = FALSE)

  seen <- character()
  for (record in records) {
    relative <- safe_relative_path(record$path)
    if (relative %in% seen) stop(sprintf("duplicate manifest path: %s", relative), call. = FALSE)
    seen <- c(seen, relative)
    path <- do.call(file.path, c(list(root), as.list(strsplit(relative, "/", fixed = TRUE)[[1]])))
    if (!file.exists(path) || dir.exists(path)) stop(sprintf("manifest file is missing: %s", relative), call. = FALSE)
    if (!identical(record$sha256, sha256_file(path))) stop(sprintf("SHA-256 mismatch: %s", relative), call. = FALSE)
    size <- unname(file.info(path)$size)
    if (!identical(as.numeric(record$size_bytes), as.numeric(size))) stop(sprintf("size mismatch: %s", relative), call. = FALSE)
  }
  distributed <- list.files(root, recursive = TRUE, full.names = FALSE, all.files = TRUE, include.dirs = FALSE)
  distributed <- gsub("\\\\", "/", distributed)
  distributed <- distributed[basename(distributed) != "release-manifest.json" & !grepl("(^|/)__pycache__(/|$)", distributed)]
  if (!identical(sort(unique(seen)), sort(unique(distributed)))) stop("manifest inventory mismatch", call. = FALSE)
  release_digest <- sha256_text(canonical_records_json(records))
  if (!identical(manifest$release_digest_sha256, release_digest)) stop("release_digest_sha256 mismatch", call. = FALSE)

  registry <- read_object(file.path(root, "registry.json"), "registry")
  if (!identical(registry$schema_version, version)) stop("registry version mismatch", call. = FALSE)
  list(root = root, manifest = manifest, registry = registry)
}

failure_class <- function(message) {
  if (grepl(" is blocked:", message, fixed = TRUE)) return("blocked_legacy_value")
  if (startsWith(message, "missing required attribute:")) return("missing_required_attribute")
  if (startsWith(message, "unknown attribute ")) return("unknown_attribute")
  if (startsWith(message, "unknown value for ")) return("unknown_registered_value")
  if (startsWith(message, "conflicting values supplied for ")) return("conflicting_alias")
  if (startsWith(message, "unknown convention group:")) return("unknown_convention")
  if (grepl(" must be ", message, fixed = TRUE) || grepl(" must contain ", message, fixed = TRUE)) {
    return("type_or_cardinality")
  }
  "semantic_validation_error"
}

make_report <- function(normalized, errors, warnings) {
  list(
    valid = length(errors) == 0L,
    normalized_attributes = normalized,
    failure_classes = unique(vapply(errors, failure_class, character(1))),
    errors = errors,
    warnings = warnings
  )
}

validate_attributes <- function(registry, convention, attributes) {
  groups <- registry$groups
  definitions <- registry$attributes
  if (is.null(groups[[convention]])) {
    return(make_report(list(), sprintf("unknown convention group: %s", convention), character()))
  }
  if (!is.list(attributes) || is.null(names(attributes))) {
    return(make_report(list(), "attributes must be an object", character()))
  }

  aliases <- registry$attribute_aliases
  canonical <- list()
  errors <- character()
  warnings <- character()
  for (supplied_name in names(attributes)) {
    target <- if (!is.null(aliases[[supplied_name]])) aliases[[supplied_name]] else supplied_name
    supplied_value <- attributes[[supplied_name]]
    if (!is.null(canonical[[target]]) && !identical(canonical[[target]], supplied_value)) {
      errors <- c(errors, sprintf("conflicting values supplied for %s through an alias", target))
    } else {
      canonical[[target]] <- supplied_value
    }
  }

  normalized <- list()
  for (name in sort(names(canonical))) {
    value <- canonical[[name]]
    definition <- definitions[[name]]
    if (is.null(definition)) {
      if (grepl(registry$extension_namespace_pattern, name, perl = TRUE)) {
        if (is.character(value) && length(value) == 1L) {
          normalized[[name]] <- value
        } else if (is.list(value) && all(vapply(value, function(x) is.character(x) && length(x) == 1L, logical(1)))) {
          normalized[[name]] <- as.list(sort(unique(unlist(value, use.names = FALSE))))
        } else {
          errors <- c(errors, sprintf("extension attribute %s must be a string or string array", name))
        }
      } else {
        errors <- c(errors, sprintf("unknown attribute %s; custom attributes must use x.<vendor>.*", name))
      }
      next
    }

    many <- identical(definition$cardinality, "many")
    if (many) {
      if (!is.list(value)) {
        errors <- c(errors, sprintf("%s must be a string array", name))
        next
      }
      if (length(value) == 0L) {
        errors <- c(errors, sprintf("%s must contain at least one value", name))
        next
      }
      if (!all(vapply(value, function(x) is.character(x) && length(x) == 1L, logical(1)))) {
        errors <- c(errors, sprintf("%s must contain only strings", name))
        next
      }
      values <- unlist(value, use.names = FALSE)
    } else {
      if (!is.character(value) || length(value) != 1L) {
        errors <- c(errors, sprintf("%s must be a string", name))
        next
      }
      values <- value
    }

    allowed <- unlist(definition$values, use.names = FALSE)
    value_aliases <- registry$value_aliases[[name]]
    blocked <- registry$blocked_legacy_values[[name]]
    output <- character()
    item_errors <- character()
    for (raw in values) {
      if (!is.null(blocked) && !is.null(blocked[[raw]])) {
        item_errors <- c(item_errors, sprintf("%s='%s' is blocked: %s", name, raw, blocked[[raw]]))
        next
      }
      item <- if (!is.null(value_aliases) && !is.null(value_aliases[[raw]])) value_aliases[[raw]] else raw
      if (!(item %in% allowed)) {
        item_errors <- c(item_errors, sprintf("unknown value for %s: '%s'", name, item))
      } else {
        output <- c(output, item)
      }
    }
    errors <- c(errors, item_errors)
    if (length(item_errors) == 0L) {
      normalized[[name]] <- if (many) as.list(sort(unique(output))) else output[[1]]
    }
  }

  requirements <- groups[[convention]]$attributes
  for (name in names(requirements)) {
    requirement <- requirements[[name]]
    if (identical(requirement, "required") && is.null(normalized[[name]])) {
      errors <- c(errors, sprintf("missing required attribute: %s", name))
    } else if (identical(requirement, "recommended") && is.null(normalized[[name]])) {
      warnings <- c(warnings, sprintf("missing recommended attribute: %s", name))
    }
  }
  make_report(normalized, errors, warnings)
}

canonicalize_json <- function(value) {
  if (!is.list(value)) return(value)
  if (is.null(names(value))) return(lapply(value, canonicalize_json))
  ordered_names <- sort(names(value))
  output <- lapply(value[ordered_names], canonicalize_json)
  names(output) <- ordered_names
  output
}

json_equal <- function(left, right) {
  identical(
    as.character(jsonlite::toJSON(canonicalize_json(left), auto_unbox = TRUE, null = "null", digits = NA)),
    as.character(jsonlite::toJSON(canonicalize_json(right), auto_unbox = TRUE, null = "null", digits = NA))
  )
}

run_conformance_suite <- function(standard_root) {
  release <- load_verified_release(standard_root)
  conformance_root <- file.path(release$root, "conformance")
  suite <- read_object(file.path(conformance_root, "manifest.json"), "conformance manifest")
  case_results <- list()
  for (case in suite$cases) {
    fixture <- read_object(file.path(conformance_root, case$input), sprintf("case %s", case$id))
    observed <- validate_attributes(release$registry, fixture$convention, fixture$attributes)
    matched <- identical(observed$valid, case$expected_valid)
    if (isTRUE(case$expected_valid)) {
      matched <- matched && json_equal(observed$normalized_attributes, case$expected_normalized_attributes)
    } else {
      matched <- matched && case$expected_failure_class %in% observed$failure_classes
    }
    case_results[[length(case_results) + 1L]] <- list(
      case_id = case$id,
      status = if (matched) "PASS" else "FAIL",
      expected_valid = case$expected_valid,
      observed_valid = observed$valid,
      normalized_attributes = observed$normalized_attributes,
      failure_classes = as.list(observed$failure_classes)
    )
  }
  status <- if (length(case_results) > 0L && all(vapply(case_results, function(x) identical(x$status, "PASS"), logical(1)))) "PASS" else "FAIL"
  list(
    schema = RESULT_SCHEMA,
    implementation = list(id = "bns019-r-jsonlite", track = "independent_validator", language = "r"),
    standard = list(
      id = STANDARD_ID,
      version = release$manifest$version,
      release_digest_sha256 = release$manifest$release_digest_sha256
    ),
    status = status,
    case_results = case_results,
    claim_boundary = "Software-contract conformance only; not certification or biological validation."
  )
}

parse_args <- function(args) {
  output <- list(standard_root = NULL, output = NULL)
  index <- 1L
  while (index <= length(args)) {
    if (args[[index]] == "--standard-root" && index < length(args)) {
      output$standard_root <- args[[index + 1L]]
      index <- index + 2L
    } else if (args[[index]] == "--output" && index < length(args)) {
      output$output <- args[[index + 1L]]
      index <- index + 2L
    } else {
      stop(sprintf("unknown or incomplete argument: %s", args[[index]]), call. = FALSE)
    }
  }
  if (is.null(output$standard_root)) stop("--standard-root is required", call. = FALSE)
  output
}

main <- function() {
  args <- parse_args(commandArgs(trailingOnly = TRUE))
  result <- run_conformance_suite(args$standard_root)
  payload <- jsonlite::toJSON(result, auto_unbox = TRUE, null = "null", digits = NA, pretty = TRUE)
  if (is.null(args$output)) {
    cat(payload, "\n", sep = "")
  } else {
    writeLines(enc2utf8(payload), args$output, useBytes = TRUE)
  }
  if (identical(result$status, "PASS")) 0L else 1L
}

if (sys.nframe() == 0L) {
  status <- tryCatch(main(), error = function(e) {
    message("ERROR: ", e$message)
    2L
  })
  quit(save = "no", status = status, runLast = FALSE)
}
