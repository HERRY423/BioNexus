"""
Create seed discussions via GitHub GraphQL API.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from bionexus.egress_guard import guarded_urlopen

TOKEN = os.environ.get("GH_TOKEN", "")
REPO_OWNER = "HERRY423"
REPO_NAME = "BioNexus"

GRAPHQL_URL = "https://api.github.com/graphql"


def graphql_query(query: str, variables: dict | None = None, max_retries: int = 5) -> dict:
    headers = {
        "Authorization": f"bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": "BioNexus-Community-Init",
    }
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    for attempt in range(1, max_retries + 1):
        try:
            req = urllib.request.Request(GRAPHQL_URL, data=payload, headers=headers, method="POST")
            with guarded_urlopen(
                req,
                timeout=30,
                purpose="GitHub discussion query",
                payload={"operation": "graphql", "variables": variables or {}},
            ) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if attempt == max_retries:
                raise
            time.sleep(2 * attempt)


def main() -> None:
    # 1. Get repository ID and discussion categories
    query = """
    query($owner: String!, $name: String!) {
      repository(owner: $owner, name: $name) {
        id
        hasDiscussionsEnabled
        discussionCategories(first: 10) {
          nodes {
            id
            name
            slug
            description
          }
        }
      }
    }
    """
    res = graphql_query(query, {"owner": REPO_OWNER, "name": REPO_NAME})
    repo_data = res.get("data", {}).get("repository")
    if not repo_data:
        print(f"Failed to query repository: {res}")
        return

    has_disc = repo_data.get("hasDiscussionsEnabled", False)
    repo_id = repo_data.get("id")
    categories = repo_data.get("discussionCategories", {}).get("nodes", [])

    print(f"Repository ID: {repo_id}")
    print(f"Discussions Enabled: {has_disc}")
    print(f"Existing Categories ({len(categories)}):")
    for cat in categories:
        print(f"  - {cat['name']} (ID: {cat['id']}, Slug: {cat['slug']})")


if __name__ == "__main__":
    main()
