"""Typed semantic memory. Hard constraints stay separate and authoritative."""

import json

from pydantic import BaseModel, Field

MAX_RECENT = 4
MAX_CONTEXT_BYTES = 6000


class MemoryFacts(BaseModel):
    preferences: list[str] = Field(default_factory=list, max_length=6)
    decisions: list[str] = Field(default_factory=list, max_length=6)
    unresolved_questions: list[str] = Field(default_factory=list, max_length=6)


def split_turns(turns):
    recent = [dict(t) for t in turns]
    older = []
    while (
        len(recent) > MAX_RECENT
        or len(json.dumps(recent, ensure_ascii=False).encode()) > 3500
    ):
        if not recent:
            break
        older.append(recent.pop(0))
    return older, recent


def render_memory(facts, recent, evicted=0):
    data = MemoryFacts.model_validate(facts).model_dump()
    # Bound each statement and the overall memory; never truncate hard constraints.
    for key in data:
        data[key] = [s.encode()[:160].decode(errors="ignore") for s in data[key]][-5:]
    summary = json.dumps(data, ensure_ascii=False) if any(data.values()) else ""
    while len(summary.encode()) > 2000:
        longest = max(data, key=lambda k: sum(len(s.encode()) for s in data[k]))
        if not data[longest]:
            break
        data[longest].pop(0)
        summary = json.dumps(data, ensure_ascii=False)
    size = len(
        json.dumps({"summary": summary, "recent": recent}, ensure_ascii=False).encode()
    )
    if size > MAX_CONTEXT_BYTES:
        raise ValueError("Active context exceeds its byte budget")
    return {
        "memory_facts": data,
        "memory_summary": summary,
        "recent_turns": recent,
        "context_bytes": size,
        "evicted_turns": evicted,
    }


def compact(turns, summary=""):
    """Deterministic semantic record for demo/tests; model mode uses Agents.remember."""
    old, recent = split_turns(turns)
    try:
        facts = (
            MemoryFacts.model_validate_json(summary).model_dump()
            if summary
            else MemoryFacts().model_dump()
        )
    except ValueError:
        facts = MemoryFacts(preferences=[summary[:160]]).model_dump()
    for turn in old:
        role = turn["role"]
        category = (
            "decisions"
            if role in {"recommendation", "human revision"}
            else "preferences"
        )
        facts[category] = (facts[category] + [turn["text"]])[-5:]
    return render_memory(facts, recent, len(old))
