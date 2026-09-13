"""Independent randomized elimination tournaments, not MCMC or posterior inference."""

import math
import random


def average_ranks(values, higher_is_better=False):
    if not values or any(not math.isfinite(v) for v in values):
        raise ValueError("Ranking requires nonempty finite observations")
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=higher_is_better)
    ranks = [0.0] * len(values)
    start = 0
    while start < len(order):
        end = start + 1
        while end < len(order) and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for i in order[start:end]:
            ranks[i] = rank
        start = end
    return ranks


def runoff(matrix, iterations=1000, seed=42):
    """Return wins and mean elimination rounds (first=1, winner=N).

    Reference implementation for correctness and small runs. National 100k runs
    need a benchmarked optimized backend before production use.
    """
    if not isinstance(iterations, int) or isinstance(iterations, bool) or iterations < 1:
        raise ValueError("iterations must be a positive integer")
    if not isinstance(seed, int) or isinstance(seed, bool):
        raise ValueError("seed must be an integer")
    if not matrix or not matrix[0]:
        raise ValueError("Runoff requires counties and factors")
    n, m = len(matrix), len(matrix[0])
    if any(len(r) != m or any(not math.isfinite(v) or v < 1 for v in r) for r in matrix):
        raise ValueError("Runoff requires a rectangular finite positive rank matrix")
    rng = random.Random(seed)
    wins, rounds = [0] * n, [0] * n
    for _ in range(iterations):
        active = list(range(n))
        factors = []
        for round_number in range(1, n):
            if not factors:
                factors = list(range(m))
                rng.shuffle(factors)
            factor = factors.pop()
            worst = max(matrix[i][factor] for i in active)
            loser = rng.choice([i for i in active if matrix[i][factor] == worst])
            rounds[loser] += round_number
            active.remove(loser)
        winner = active[0]
        wins[winner] += 1
        rounds[winner] += n
    return wins, [v / iterations for v in rounds]
