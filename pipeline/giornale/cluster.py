"""Raggruppamento delle voci che parlano dello stesso fatto (prima passata, senza modello)."""
from __future__ import annotations

from dataclasses import dataclass, field

from .feeds import Item
from .textutil import jaccard, tokens


@dataclass
class Cluster:
    cid: str
    items: list[Item] = field(default_factory=list)

    @property
    def lead(self) -> Item:
        # titolo rappresentativo: preferisce fonti primarie, poi la voce più recente
        return sorted(self.items, key=lambda i: (i.source_kind != "primaria", -(i.published.timestamp() if i.published else 0)))[0]

    @property
    def domains(self) -> set[str]:
        return {i.domain for i in self.items}

    def describe(self, summary_chars: int = 180) -> str:
        lead = self.lead
        when = lead.published.strftime("%d/%m %H:%M") if lead.published else "?"
        others = sorted({i.source_name for i in self.items} - {lead.source_name})
        extra = f" (+{', '.join(others)})" if others else ""
        summary = lead.summary[:summary_chars].replace("\n", " ")
        return f"{self.cid} | [{lead.source_name}{extra}] {lead.title} ({when} UTC) | {summary}"


def cluster_items(items: list[Item], threshold: float = 0.45) -> list[Cluster]:
    toks = [tokens(f"{it.title}") for it in items]
    parent = list(range(len(items)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i].key == items[j].key:
                parent[find(j)] = find(i)
                continue
            if len(toks[i]) < 3 or len(toks[j]) < 3:
                continue
            if jaccard(toks[i], toks[j]) >= threshold:
                parent[find(j)] = find(i)

    groups: dict[int, list[Item]] = {}
    for idx, it in enumerate(items):
        groups.setdefault(find(idx), []).append(it)

    ordered = sorted(groups.values(), key=lambda g: -max(i.published.timestamp() for i in g if i.published))
    return [Cluster(cid=f"C{n + 1}", items=g) for n, g in enumerate(ordered)]
