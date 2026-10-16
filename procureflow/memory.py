"""Bounded active context with extractive summaries. Durable full audit stays in checkpoints."""

import json

MAX_RECENT = 4
MAX_CONTEXT_BYTES = 6000


def compact(turns, summary=""):
    recent = [
        {**t, "text": t["text"].encode("utf-8")[:2000].decode("utf-8", errors="ignore")}
        for t in turns
    ]
    evicted = []
    while (
        len(recent) > MAX_RECENT
        or len(json.dumps(recent, ensure_ascii=False).encode()) > 4000
    ):
        if len(recent) <= 1:
            break
        evicted.append(recent.pop(0))
    # Structured extractive summary avoids model hallucinations and extra inference.
    for turn in evicted:
        summary += f"\n{turn['role']}: {turn['text'][:500]}"
    summary = summary.encode("utf-8")[-1800:].decode("utf-8", errors="ignore")
    context = {"summary": summary, "recent": recent}
    if len(json.dumps(context, ensure_ascii=False).encode()) > MAX_CONTEXT_BYTES:
        raise ValueError("Active context exceeds its byte budget")
    # UTF-8 bytes bound tokens conservatively for byte-based tokenizers; actual Ollama
    # prompt_eval_count is reported separately, not mislabeled as an exact estimate.
    return {
        "memory_summary": summary,
        "recent_turns": recent,
        "context_bytes": len(json.dumps(context, ensure_ascii=False).encode()),
        "evicted_turns": len(evicted),
    }
