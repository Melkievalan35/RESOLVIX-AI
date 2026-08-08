from typing import List, Dict

def rerank(query: str, candidates: List[Dict]):
    return sorted(
        candidates,
        key=lambda x: x.get("score", 0),
        reverse=True,
    )