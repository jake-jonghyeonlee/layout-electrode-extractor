"""Exact reachability in the Z² lift of a finite displacement graph.

Nodes are components inside one unit. An edge (u, v, dx, dy) means an
edge from (u, tile) to (v, tile + (dx, dy)). Tree potentials identify each
node with a root; cycle displacements generate a subgroup of Z². Two lifted
nodes are connected exactly when their potential-adjusted tile difference
belongs to that subgroup. No finite halo or convergence heuristic is used.
"""

from __future__ import annotations

from collections import deque
from math import gcd

import numpy as np
from scipy import ndimage


class ResourceError(ValueError):
    """A requested graph or output exceeds the documented safety limit."""


def label_mask(mask: np.ndarray, connectivity: int) -> tuple[np.ndarray, int]:
    structure = ndimage.generate_binary_structure(2, 1 if connectivity == 4 else 2)
    labels, count = ndimage.label(mask, structure=structure)
    return labels.astype(np.int32, copy=False), int(count)


def _bezout(a: int, b: int) -> tuple[int, int, int]:
    """Return nonnegative gcd and signed coefficients."""
    old_r, r = abs(a), abs(b)
    old_s, s = 1, 0
    old_t, t = 0, 1
    while r:
        q = old_r // r
        old_r, r = r, old_r - q * r
        old_s, s = s, old_s - q * s
        old_t, t = t, old_t - q * t
    return old_r, old_s * (1 if a >= 0 else -1), old_t * (1 if b >= 0 else -1)


class Lattice:
    """Incremental rank 0/1/2 subgroup of integer tile displacements."""

    def __init__(self) -> None:
        self.rank = 0
        self.vector = (0, 0)
        self.gx = 0
        self.yr = 0
        self.gv = 0

    def add(self, vector: tuple[int, int]) -> None:
        x, y = vector
        if x == y == 0:
            return
        if self.rank == 0:
            self.vector = vector
            self.rank = 1
            return
        if self.rank == 1:
            a, b = self.vector
            det = a * y - b * x
            if det == 0:
                g = gcd(abs(a), abs(b))
                px, py = a // g, b // g
                coefficient = x // px if px else y // py
                step = gcd(g, abs(coefficient))
                self.vector = (px * step, py * step)
                return
            self.gx, p, q = _bezout(a, x)
            self.gv = abs(det) // self.gx
            self.yr = (p * b + q * y) % self.gv
            self.rank = 2
            return
        old_gx, old_yr, old_gv = self.gx, self.yr, self.gv
        new_gx, p, q = _bezout(old_gx, x)
        index = gcd(old_gx * old_gv, old_gx * y - old_yr * x, old_gv * x)
        self.gx = new_gx
        self.gv = index // new_gx
        self.yr = (p * old_yr + q * y) % self.gv

    def key(self, vector: tuple[int, int]) -> tuple[int, int]:
        x, y = vector
        if self.rank == 0:
            return vector
        if self.rank == 1:
            a, b = self.vector
            step = gcd(abs(a), abs(b))
            px, py = a // step, b // step
            _, u, v = _bezout(px, py)
            return (px * y - py * x, (u * x + v * y) % step)
        quotient, remainder = divmod(x, self.gx)
        return remainder, (y - quotient * self.yr) % self.gv

    def description(self) -> dict:
        if self.rank == 0:
            return {"rank": 0, "generators": []}
        if self.rank == 1:
            return {"rank": 1, "generators": [list(self.vector)]}
        return {"rank": 2, "generators": [[self.gx, self.yr], [0, self.gv]]}


class PeriodicGraph:
    def __init__(self, max_nodes: int = 100_000, max_edges: int = 1_000_000) -> None:
        self.names: list[tuple[str, int]] = []
        self.lookup: dict[tuple[str, int], int] = {}
        self.edges: list[tuple[int, int, int, int]] = []
        self.max_nodes = max_nodes
        self.max_edges = max_edges
        self.component: list[int] = []
        self.potential: list[tuple[int, int]] = []
        self.lattices: list[Lattice] = []

    def add_nodes(self, layer: str, count: int) -> None:
        if len(self.names) + count > self.max_nodes:
            raise ResourceError(f"more than {self.max_nodes} components")
        for local in range(1, count + 1):
            self.lookup[layer, local] = len(self.names)
            self.names.append((layer, local))

    def add_edge(self, u: int, v: int, dx: int = 0, dy: int = 0) -> None:
        if len(self.edges) >= self.max_edges:
            raise ResourceError(f"more than {self.max_edges} graph edges")
        self.edges.append((u, v, dx, dy))

    def add_periodic_boundaries(self, layer: str, labels: np.ndarray, connectivity: int) -> None:
        h, w = labels.shape
        shifts = [(1, 0), (0, 1)]
        if connectivity == 8:
            shifts += [(1, 1), (-1, 1)]
        for sx, sy in shifts:
            points: list[tuple[int, int]] = []
            if sx:
                xb = w - 1 if sx == 1 else 0
                points.extend((xb, y) for y in range(h))
            if sy:
                points.extend((x, h - 1) for x in range(w) if not sx or x != xb)
            for x, y in points:
                nx, ny = x + sx, y + sy
                tx = -1 if nx < 0 else 1 if nx >= w else 0
                ty = -1 if ny < 0 else 1 if ny >= h else 0
                left = int(labels[y, x])
                right = int(labels[ny % h, nx % w])
                if left and right:
                    self.add_edge(self.lookup[layer, left], self.lookup[layer, right], tx, ty)

    def solve(self) -> None:
        adj: list[list[tuple[int, int, int]]] = [[] for _ in self.names]
        for u, v, dx, dy in self.edges:
            adj[u].append((v, dx, dy))
            adj[v].append((u, -dx, -dy))
        n = len(self.names)
        self.component = [-1] * n
        self.potential = [(0, 0)] * n
        self.lattices = []
        for root in range(n):
            if self.component[root] >= 0:
                continue
            component = len(self.lattices)
            lattice = Lattice()
            self.lattices.append(lattice)
            self.component[root] = component
            queue = deque([root])
            while queue:
                u = queue.popleft()
                ux, uy = self.potential[u]
                for v, dx, dy in adj[u]:
                    proposed = ux + dx, uy + dy
                    if self.component[v] == -1:
                        self.component[v] = component
                        self.potential[v] = proposed
                        queue.append(v)
                    else:
                        assert self.component[v] == component
                        vx, vy = self.potential[v]
                        lattice.add((proposed[0] - vx, proposed[1] - vy))

    def key(self, node: int, tile_x: int, tile_y: int) -> tuple[int, tuple[int, int]]:
        px, py = self.potential[node]
        component = self.component[node]
        return component, self.lattices[component].key((tile_x - px, tile_y - py))

    def describe(self) -> dict:
        return {
            "node_count": len(self.names),
            "edge_count": len(self.edges),
            "components": [lattice.description() for lattice in self.lattices],
            "edges": [
                {"from": list(self.names[u]), "to": list(self.names[v]), "displacement": [dx, dy]}
                for u, v, dx, dy in self.edges
            ],
        }
