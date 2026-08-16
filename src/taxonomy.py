"""Topic taxonomy: rule-based tagging from config/taxonomy.yml, with
session-judgment labels for leftovers merged from cache/topic_labels.json
({"<video_or_post_id>": "<label>"} authored by the routine session).

Tags are immutable once written to the ledger - enforced by
common.append_history / update_history_rows, which only ever FILL an empty
topic and never overwrite a non-empty one.
"""
from __future__ import annotations

import yaml

from . import common


def load_taxonomy() -> list[dict]:
    with open(common.taxonomy_path(), "r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return data.get("labels", [])


def valid_labels(taxonomy: list[dict] | None = None) -> set[str]:
    return {e["label"] for e in (taxonomy or load_taxonomy())}


def tag_title(title: str, taxonomy: list[dict]) -> str:
    """Label whose LONGEST hint substring-matches the title; '' if none.
    Specificity wins ('pending syllabus' beats 'syllabus'); ties resolve by
    taxonomy.yml order (earlier label wins)."""
    t = f" {(title or '').lower()} "
    best_label, best_len, best_idx = "", 0, len(taxonomy)
    for idx, entry in enumerate(taxonomy):
        for hint in entry.get("hints", []):
            if hint in t and (len(hint) > best_len
                              or (len(hint) == best_len and idx < best_idx)):
                best_label, best_len, best_idx = entry["label"], len(hint), idx
    return best_label


def load_session_labels(taxonomy: list[dict] | None = None) -> dict:
    """Session-authored labels for rule leftovers; invalid labels dropped."""
    raw = common.read_json(common.cache_path("topic_labels.json"), {}) or {}
    valid = valid_labels(taxonomy)
    return {k: v for k, v in raw.items() if v in valid}


def tag_candidate(c: dict, taxonomy: list[dict], session_labels: dict) -> str:
    """Rules first, then session judgment; '' stays pending for the session
    (merge re-run fills it; final fallback to 'misc' is the session's call)."""
    key = c.get("video_id") or c.get("post_url") or ""
    rule = tag_title(c.get("title", ""), taxonomy)
    if rule:
        return rule
    return session_labels.get(key, "")
