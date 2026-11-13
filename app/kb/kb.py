"""Knowledge base over GOST terms, references and section outlines."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict, deque
from pathlib import Path

WS_RE = re.compile(r"\s+")
NORM_RE = re.compile(r"[^а-яёa-z0-9 ]+")


def norm_text(text: str) -> str:
    return WS_RE.sub(" ", NORM_RE.sub(" ", text.lower())).strip()


def norm_gost(text: str) -> str:
    return norm_text(text).replace(" ", "")


class KnowledgeBase:
    def __init__(self, kb_dir: Path | None = None) -> None:
        self.dir = Path(kb_dir or os.getenv("DATA_KB_DIR", "data/kb"))
        self.graph = json.loads((self.dir / "graph.json").read_text(encoding="utf-8"))
        self.outline_data = json.loads((self.dir / "outline.json").read_text(encoding="utf-8"))
        self.terms = [
            json.loads(line)
            for line in (self.dir / "terms.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.nodes = {node["gost"]: node for node in self.graph["nodes"]}
        self.out_edges: dict[str, list[dict]] = defaultdict(list)
        self.in_edges: dict[str, list[dict]] = defaultdict(list)
        for edge in self.graph["edges"]:
            self.out_edges[edge["source"]].append(edge)
            self.in_edges[edge["target"]].append(edge)
        self.by_term: dict[str, list[dict]] = defaultdict(list)
        self.by_alias: dict[str, list[dict]] = defaultdict(list)
        for term in self.terms:
            self.by_term[term["term_norm"]].append(term)
            for alias in term.get("aliases", []):
                alias_norm = norm_text(alias)
                if alias_norm:
                    self.by_alias[alias_norm].append(term)

    def find_term(self, query: str, gost: str | None = None, limit: int = 3) -> list[dict]:
        query_norm = norm_text(query)
        if not query_norm:
            return []
        candidates: list[tuple[float, dict]] = []
        for term in self.terms:
            if gost and term["gost"] != gost:
                continue
            name = term["term_norm"]
            aliases = [norm_text(alias) for alias in term.get("aliases", [])]
            score = 0.0
            if query_norm == name or query_norm in aliases:
                score = 10.0
            elif query_norm in name or name in query_norm:
                score = 6.0
            elif any(alias and (alias in query_norm or query_norm in alias) for alias in aliases):
                score = 5.0
            else:
                query_tokens = {token[:5] for token in query_norm.split() if len(token) >= 3}
                term_tokens = {token[:5] for token in name.split() if len(token) >= 3}
                if query_tokens:
                    overlap = len(query_tokens & term_tokens) / len(query_tokens)
                    if overlap >= 0.6:
                        score = 3.0 * overlap
            if score:
                candidates.append((score, term))
        candidates.sort(key=lambda pair: (pair[0], len(pair[1]["definition"])), reverse=True)
        return [term for _, term in candidates[:limit]]

    def find_gost(self, query: str) -> str | None:
        target = norm_gost(query)
        if not target:
            return None
        for gost in self.nodes:
            if norm_gost(gost) == target:
                return gost
        for gost in self.nodes:
            if target in norm_gost(gost) or norm_gost(gost) in target:
                return gost
        return None

    def outline(self, gost: str) -> dict | None:
        found = self.find_gost(gost)
        return self.outline_data.get(found) if found else None

    def neighbors(
        self, gost: str, internal_only: bool = False, limit: int = 50
    ) -> dict[str, list[dict] | str]:
        found = self.find_gost(gost) or gost
        outgoing = [
            edge
            for edge in self.out_edges.get(found, [])
            if not internal_only or edge["internal"]
        ][:limit]
        incoming = [
            edge
            for edge in self.in_edges.get(found, [])
            if not internal_only or edge["internal"]
        ][:limit]
        return {"gost": found, "outgoing": outgoing, "incoming": incoming}

    def external_neighbors(self, gost: str, limit: int = 50) -> list[dict]:
        """Outgoing references to standards outside the corpus, deduped and ordered."""
        found = self.find_gost(gost) or gost
        edges = [
            edge for edge in self.out_edges.get(found, []) if not edge.get("internal", False)
        ]
        seen: set[str] = set()
        result: list[dict] = []
        for edge in sorted(
            edges,
            key=lambda item: (
                int(item.get("page", 0) or 0),
                str(item.get("clause", "")),
            ),
        ):
            target = str(edge.get("target", ""))
            if not target or target in seen:
                continue
            seen.add(target)
            result.append(edge)
        return result[:limit]

    def path(self, source: str, target: str) -> list[str]:
        start = self.find_gost(source) or source
        goal = self.find_gost(target) or target
        if start not in self.nodes or goal not in self.nodes:
            return []
        queue = deque([(start, [start])])
        seen = {start}
        while queue:
            node, route = queue.popleft()
            if node == goal:
                return route
            edges = self.out_edges.get(node, []) + self.in_edges.get(node, [])
            for edge in edges:
                if not edge["internal"]:
                    continue
                nxt = edge["target"] if edge["source"] == node else edge["source"]
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append((nxt, route + [nxt]))
        return []

    def expand_query(self, query: str, limit: int = 3) -> list[str]:
        query_norm = norm_text(query)
        if not query_norm:
            return []
        matches: list[tuple[int, dict]] = []
        for term in self.terms:
            values = [term["term_norm"]] + [
                norm_text(alias) for alias in term.get("aliases", [])
            ]
            best = max(
                (len(value) for value in values if len(value) >= 2 and value in query_norm),
                default=0,
            )
            if best:
                matches.append((best, term))
        matches.sort(key=lambda pair: pair[0], reverse=True)
        result: list[str] = []
        selected: list[dict] = []
        seen_concepts: set[str] = set()
        for _, term in matches:
            concept = " ".join(term["term_norm"].split()[:2])
            if concept in seen_concepts:
                continue
            seen_concepts.add(concept)
            selected.append(term)
            value = term["term"].strip()
            if value and value.lower() not in {item.lower() for item in result}:
                result.append(value)
            if len(result) >= limit:
                return result[:limit]
        for term in selected:
            for value in term.get("aliases", []):
                value = value.strip()
                if value and value.lower() not in {item.lower() for item in result}:
                    result.append(value)
                if len(result) >= limit:
                    return result[:limit]
        return result[:limit]

    def stats(self) -> dict:
        return dict(self.graph.get("meta", {}))

