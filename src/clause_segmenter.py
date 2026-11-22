import re
from typing import List, Dict

_EN_CLAUSE = re.compile(r"(?:CLAUSE|ARTICLE|Section)\s+(\d+[A-Za-z]?)", re.IGNORECASE)
_AR_CLAUSE = re.compile(r"(?:البند|المادة)\s+(\d+[A-Za-z]?)")


def _sort_key(clause_id: str):
    """
    Sort clause IDs numerically: "4" < "9" < "14" < "20".
    Handles letter suffixes ("4A" < "4B") and the "ALL" fallback.

    Returns a tuple (is_ALL_flag, numeric_prefix, suffix):
      - "ALL" sorts last
      - Numeric IDs sort by integer value, then suffix
      - Non-numeric IDs sort after all numeric IDs (alphabetically)
    """
    if clause_id == "ALL":
        return (1, 0, "")
    match = re.match(r"^(\d+)(.*)$", clause_id)
    if match:
        return (0, int(match.group(1)), match.group(2))
    return (0, float("inf"), clause_id)


def segment_clauses(text: str, lang: str) -> Dict[str, str]:
    """
    Returns {clause_id: clause_text}.
    clause_id is the numeric token as a string, e.g. "4", "9", "14", or "4A".
    Falls back to {"ALL": text} if no clause headers are detected.
    """
    if not text or not text.strip():
        return {}
    pattern = _EN_CLAUSE if lang == "en" else _AR_CLAUSE
    matches = list(pattern.finditer(text))
    if not matches:
        return {"ALL": text.strip()}
    clauses: Dict[str, str] = {}
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        clauses[m.group(1)] = text[start:end].strip()
    return clauses


def align_bilingual_clauses(en_text: str, ar_text: str) -> List[Dict[str, str]]:
    """
    Pairs English and Arabic clauses by numeric ID.
    Returns list of {"clause_id", "en", "ar"} in numeric clause order,
    with empty strings where one side is missing.
    """
    en_map = segment_clauses(en_text, "en")
    ar_map = segment_clauses(ar_text, "ar")
    all_ids = sorted(set(en_map) | set(ar_map), key=_sort_key)
    return [
        {"clause_id": cid, "en": en_map.get(cid, ""), "ar": ar_map.get(cid, "")}
        for cid in all_ids
    ]