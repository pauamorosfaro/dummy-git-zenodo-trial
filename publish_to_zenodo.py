#!/usr/bin/env python3
"""Publish selected repository files as a new version of an existing Zenodo record."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import requests

API_BASE = "https://sandbox.zenodo.org/api"
TIMEOUT = 60


def require_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required environment variable {name} is missing.")
    return value


def check(response: requests.Response, action: str) -> requests.Response:
    if not response.ok:
        try:
            detail = response.json()
        except ValueError:
            detail = response.text
        raise RuntimeError(
            f"{action} failed with HTTP {response.status_code}: {detail}"
        )
    return response


def latest_record_id(session: requests.Session, concept_id: str) -> int:
    response = check(
        session.get(
            f"{API_BASE}/records",
            params={
                "q": f"conceptrecid:{concept_id}",
                "all_versions": "true",
                "sort": "mostrecent",
                "size": 100,
            },
            timeout=TIMEOUT,
        ),
        "Finding the latest published Zenodo version",
    )
    hits = response.json().get("hits", {}).get("hits", [])
    if not hits:
        raise RuntimeError(
            f"No published record was found for concept ID {concept_id}."
        )
    return max(int(hit["id"]) for hit in hits)


def create_or_reuse_draft(
    session: requests.Session,
    latest_id: int,
) -> dict[str, Any]:
    response = check(
        session.post(
            f"{API_BASE}/deposit/depositions/{latest_id}/actions/newversion",
            timeout=TIMEOUT,
        ),
        "Creating the new Zenodo version",
    )
    latest_draft_url = response.json().get("links", {}).get("latest_draft")
    if not latest_draft_url:
        raise RuntimeError("Zenodo did not return a latest_draft link.")

    return check(
        session.get(latest_draft_url, timeout=TIMEOUT),
        "Opening the new-version draft",
    ).json()


def replace_files(
    session: requests.Session,
    draft: dict[str, Any],
    paths: list[Path],
) -> None:
    draft_id = int(draft["id"])
    files_url = draft["links"]["files"]

    existing_files = check(
        session.get(files_url, timeout=TIMEOUT),
        "Listing inherited Zenodo files",
    ).json()

    for item in existing_files:
        file_id = item["id"]
        check(
            session.delete(
                f"{API_BASE}/deposit/depositions/{draft_id}/files/{file_id}",
                timeout=TIMEOUT,
            ),
            f"Deleting inherited file {item.get('filename', file_id)}",
        )

    bucket_url = draft["links"]["bucket"].rstrip("/")
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Release file not found: {path}")

        with path.open("rb") as handle:
            check(
                session.put(
                    f"{bucket_url}/{path.name}",
                    data=handle,
                    timeout=300,
                ),
                f"Uploading {path}",
            )


def update_metadata(
    session: requests.Session,
    draft: dict[str, Any],
    version: str,
    release_url: str,
    publication_date: str,
) -> dict[str, Any]:
    metadata = dict(draft["metadata"])
    metadata["version"] = version
    metadata["publication_date"] = publication_date

    related = list(metadata.get("related_identifiers", []))
    relation = {
        "identifier": release_url,
        "relation": "isSupplementedBy",
        "resource_type": "other",
    }
    if not any(item.get("identifier") == release_url for item in related):
        related.append(relation)
    metadata["related_identifiers"] = related

    return check(
        session.put(
            draft["links"]["self"],
            json={"metadata": metadata},
            timeout=TIMEOUT,
        ),
        "Updating Zenodo metadata",
    ).json()


def main() -> None:
    token = require_env("ZENODO_SANDBOX_TOKEN")
    concept_id = require_env("ZENODO_SANDBOX_CONCEPT_ID")
    tag = require_env("GITHUB_RELEASE_TAG")
    release_url = require_env("GITHUB_RELEASE_URL")
    published_at = os.environ.get("GITHUB_RELEASE_PUBLISHED_AT", "").strip()

    version = tag[1:] if tag.lower().startswith("v") else tag
    publication_date = (
        published_at[:10] if published_at else date.today().isoformat()
    )

    if len(sys.argv) < 2:
        raise RuntimeError("Pass at least one repository file to upload.")
    paths = [Path(arg) for arg in sys.argv[1:]]

    session = requests.Session()
    session.headers.update({"Authorization": f"Bearer {token}"})

    latest_id = latest_record_id(session, concept_id)
    print(f"Latest published Zenodo record: {latest_id}")

    draft = create_or_reuse_draft(session, latest_id)
    print(f"New-version draft: {draft['id']}")

    replace_files(session, draft, paths)
    draft = update_metadata(
        session,
        draft,
        version,
        release_url,
        publication_date,
    )

    published = check(
        session.post(draft["links"]["publish"], timeout=TIMEOUT),
        "Publishing the Zenodo version",
    ).json()

    doi = published.get("doi") or published.get("metadata", {}).get(
        "prereserve_doi", {}
    ).get("doi")
    print(
        f"Published Zenodo version {version}. "
        f"DOI: {doi or 'see Zenodo record'}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
