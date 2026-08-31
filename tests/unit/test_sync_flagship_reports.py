from scripts.sync_flagship_reports import source_snapshots, sync_nested_provenance


def test_sync_preserves_dependency_version_and_updates_stale_source_identity() -> None:
    document = {
        "pipeline": {
            "version": "1.0.0-rc.3",
            "backend_identity": {"version": "0.5.4"},
            "provenance": {
                "commit_sha": "old-commit",
                "source_snapshot_sha256": "old-snapshot",
            },
        }
    }

    assert source_snapshots(document) == {"old-snapshot"}
    sync_nested_provenance(
        document,
        "new-commit",
        "new-snapshot",
        update_commit=True,
    )

    assert document["pipeline"]["version"] == "1.0.0-rc.3"
    assert document["pipeline"]["backend_identity"]["version"] == "0.5.4"
    assert document["pipeline"]["provenance"]["commit_sha"] == "new-commit"
    assert document["pipeline"]["provenance"]["source_snapshot_sha256"] == "new-snapshot"


def test_sync_preserves_source_commit_when_snapshot_is_current() -> None:
    document = {
        "commit_sha": "validated-source-commit",
        "source_snapshot_sha256": "current-snapshot",
    }

    sync_nested_provenance(
        document,
        "merge-commit",
        "current-snapshot",
        update_commit=False,
    )

    assert document["commit_sha"] == "validated-source-commit"
