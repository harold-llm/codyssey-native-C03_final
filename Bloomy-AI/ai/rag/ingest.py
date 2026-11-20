"""Validate catalog metadata and split each item into attributable chunks."""
import json
from pathlib import Path

SKILLS = {"listening", "speaking", "reading", "writing"}
TYPES = {"readers_series", "phonics", "worksheet", "video", "audio", "activity"}


def validate_catalog(items):
    if not isinstance(items, list):
        raise ValueError("catalog must be a JSON array")
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("catalog entries must be objects")
        for key in ("id", "title", "expert_note", "trust_source", "link"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"missing or empty catalog field: {key}")
        if item["id"] in seen:
            raise ValueError(f"duplicate content_id: {item['id']}")
        seen.add(item["id"])
        for key, low, high in (("age_min", 4, 7), ("age_max", 4, 7), ("level", 1, 5)):
            if type(item.get(key)) is not int or not low <= item[key] <= high:
                raise ValueError(f"invalid {key}: {item['id']}")
        if item["age_min"] > item["age_max"]:
            raise ValueError("age_min exceeds age_max")
        if item.get("skill") not in SKILLS or item.get("type") not in TYPES:
            raise ValueError("invalid skill or type")
        if item.get("provider") not in {"purchase", "link"}:
            raise ValueError("invalid provider")
        if type(item.get("session_minutes")) is not int or item["session_minutes"] not in (10, 15, 20):
            raise ValueError("invalid session_minutes")
        if not item["link"].startswith("https://"):
            raise ValueError("catalog links must use https")
        required_text = ("task", "check_point")
        if "learning_goal" in item:
            required_text += ("learning_goal",)
        for key in required_text:
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ValueError(f"missing learning instruction: {key}")
    return items


def load_catalog(path):
    return validate_catalog(json.loads(Path(path).read_text(encoding="utf-8")))


def make_chunks(items):
    chunks = []
    for item in items:
        for kind, text in (("overview", item["title"]), ("guidance", item["expert_note"]),
                           ("practice", item["task"] + " " + item["check_point"])):
            chunks.append({"chunk_id": f"{item['id']}:{kind}", "content_id": item["id"],
                           "text": text, "source": item["trust_source"]})
    return chunks
