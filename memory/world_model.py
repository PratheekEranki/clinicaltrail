"""Meterless World Model wrapper — shared entity store.

Keeps "T2DM" and "type 2 diabetes" pointing at the same entity so every agent
uses consistent terminology. In-process until the Meterless SDK is confirmed.
"""
import uuid

_SESSIONS: dict[str, "WorldModel"] = {}

# Common clinical abbreviations → canonical names
SYNONYMS = {
    "t2dm": "type 2 diabetes",
    "t2d": "type 2 diabetes",
    "type ii diabetes": "type 2 diabetes",
    "diabetes mellitus type 2": "type 2 diabetes",
    "t1dm": "type 1 diabetes",
    "acei": "ace inhibitor",
    "acei's": "ace inhibitor",
    "ace inhibitors": "ace inhibitor",
    "arb": "angiotensin receptor blocker",
    "arbs": "angiotensin receptor blocker",
    "mace": "major adverse cardiovascular events",
    "cvd": "cardiovascular disease",
    "htn": "hypertension",
    "ckd": "chronic kidney disease",
    "mi": "myocardial infarction",
    "elderly": "older adults (65+)",
}


def canonical(name: str) -> str:
    key = name.strip().lower()
    return SYNONYMS.get(key, key)


class WorldModel:
    def __init__(self, session_id: str | None = None):
        self.session_id = session_id or f"wm-{uuid.uuid4().hex[:12]}"
        self._entities: dict[str, dict] = {}   # canonical name → entity
        self._facts: list[dict] = []

    @classmethod
    def session(cls, session_id: str | None = None) -> "WorldModel":
        if session_id and session_id in _SESSIONS:
            return _SESSIONS[session_id]
        wm = cls(session_id)
        _SESSIONS[wm.session_id] = wm
        return wm

    def add_entity(self, name: str, entity_type: str) -> dict:
        canon = canonical(name)
        ent = self._entities.setdefault(canon, {
            "id": f"ent-{len(self._entities) + 1}",
            "name": canon,
            "type": entity_type,
            "aliases": set(),
        })
        if name.strip().lower() != canon:
            ent["aliases"].add(name.strip())
        return ent

    def assert_fact(self, subject: str, predicate: str, object: str) -> None:
        self._facts.append({"subject": canonical(subject), "predicate": predicate,
                            "object": canonical(object)})

    def find_entity(self, name: str, entity_type: str | None = None) -> list[dict]:
        canon = canonical(name)
        return [self._public(e) for e in self._entities.values()
                if (e["name"] == canon or canon in e["name"])
                and (entity_type is None or e["type"] == entity_type)]

    def get_relationships(self, entity_id: str) -> list[dict]:
        names = {e["name"] for e in self._entities.values() if e["id"] == entity_id}
        return [f for f in self._facts if f["subject"] in names or f["object"] in names]

    def all_entities(self) -> list[dict]:
        return [self._public(e) for e in self._entities.values()]

    def normalize(self, text: str) -> str:
        """Append canonical names for any alias found in text (keeps the original words)."""
        lowered = f" {text.lower()} "
        extras = [canon for alias, canon in SYNONYMS.items()
                  if f" {alias} " in lowered and canon not in lowered]
        for ent in self._entities.values():
            if any(a.lower() in lowered for a in ent["aliases"]) and ent["name"] not in lowered:
                extras.append(ent["name"])
        return f"{text} ({', '.join(dict.fromkeys(extras))})" if extras else text

    @staticmethod
    def _public(ent: dict) -> dict:
        return {**ent, "aliases": sorted(ent["aliases"])}
