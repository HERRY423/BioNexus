# Launch attempt 01 superseded

The first launch bundle registered the aggregate 54-case input-manifest digest
as the sole development-dataset digest. That aggregate binds the local package,
but it cannot directly match a new case's individual dataset digest in the
production overlap check. The files are retained and are not an executed pilot.

The corrected final bundle lists the individual
nonzero `counts_sha256` values from the frozen development receipts, so a case
using a recorded development dataset is excluded by the existing scorer.
