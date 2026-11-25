"""Deterministic local sparse-vector retrieval. No API or model downloads."""
import math
import re
from collections import Counter
from typing import Protocol

from .materials import is_owned as is_owned_material

ALIASES = {"듣기": "listening", "말하기": "speaking", "읽기": "reading", "쓰기": "writing", "파닉스": "phonics"}


def tokens(text):
    text = text.casefold()
    for key, value in ALIASES.items():
        text = text.replace(key, value)
    words = re.findall(r"[a-z0-9]+|[가-힣]+", text)
    return words + [w[i:i+2] for w in words if re.search(r"[가-힣]", w) for i in range(len(w)-1)]


class Retriever(Protocol):
    def search(self, request) -> list[dict]: ...


class LocalRetriever:
    def __init__(self, catalog, chunks):
        self.catalog = catalog
        self.chunks = chunks
        self.vectors = [Counter(tokens(c["text"])) for c in chunks]
        df = Counter(t for vector in self.vectors for t in vector)
        self.idf = {t: math.log((1 + len(chunks)) / (1 + n)) + 1 for t, n in df.items()}

    def similarity(self, query, vector):
        def weight(v, t):
            return v[t] * self.idf.get(t, 1.0)
        numerator = sum(weight(query, t) * weight(vector, t) for t in query.keys() & vector.keys())
        denominator = math.sqrt(sum(weight(query, t)**2 for t in query)) * math.sqrt(sum(weight(vector, t)**2 for t in vector))
        return numerator / denominator if denominator else 0.0

    def search(self, request):
        query = Counter(tokens(" ".join((request.goal, *request.favorite_topics))))
        skill_terms = tokens(request.goal)
        hits = []
        for item in self.catalog:
            is_owned = is_owned_material(item, request.owned_materials)
            # 보유 교재는 1회 길이가 설정보다 길어도 후보로 두고, 카드 분량을 설정 시간에 맞춘다.
            if not (item["age_min"] <= request.age <= item["age_max"] and item["level"] == request.base_level
                    and (is_owned or item["session_minutes"] <= request.session_minutes)):
                continue
            candidates = [(self.similarity(query, v), c) for c, v in zip(self.chunks, self.vectors) if c["content_id"] == item["id"]]
            similarity, chunk = max(candidates, key=lambda pair: (pair[0], pair[1]["chunk_id"]))
            skill_match = item["skill"] in skill_terms or item["type"] in skill_terms
            score = similarity + (1 if skill_match else 0)
            hits.append({"item": item, "score": round(score, 6), "owned": is_owned,
                         "chunk_id": chunk["chunk_id"], "excerpt": chunk["text"], "source": chunk["source"]})
        # Ownership is an explicit priority, followed by relevance and stable ID.
        return sorted(hits, key=lambda h: (not h["owned"], -h["score"], h["item"]["id"]))[:request.top_k]
