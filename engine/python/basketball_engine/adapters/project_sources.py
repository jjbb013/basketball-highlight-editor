"""Name-only grouping for local, cross-project highlight exports."""
from __future__ import annotations

import unicodedata
from typing import Any


def normalized_player_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    return unicodedata.normalize("NFKC", value).strip() or None


def player_group_key(candidate: dict[str, Any]) -> str:
    name = normalized_player_name(candidate.get("player_name"))
    if name:
        return f"name:{name.casefold()}"
    project = candidate.get("source_project")
    project_id = project.get("id") if isinstance(project, dict) else None
    return f"unassigned:{project_id or candidate.get('source_project_id') or 'current'}"


def group_player_candidates(
    candidates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        groups.setdefault(player_group_key(candidate), []).append(candidate)
    return groups
