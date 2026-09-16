# Launch attempt 02 setup failure

The second launch build stopped while collecting development dataset hashes
because the deliberately missing-receipt control stores JSON `null`. No plan,
status, manifest, provenance record, or ZIP was generated in this attempt.

The corrected builder ignores non-object receipt documents while retaining them
as negative controls. It writes the next launch to `attempt-03/`.
