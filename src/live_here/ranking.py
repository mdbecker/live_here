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


def _select_set_bit(mask, index):
    """Return the index-th set bit in ascending bit order."""
    if index < 0 or index >= mask.bit_count():
        raise IndexError("set-bit index out of range")

    # Binary search the bit position using C-level integer bit counts. This
    # preserves the active-list order used by the reference implementation
    # without rebuilding a Python list of tied counties.
    low, high = 0, mask.bit_length()
    while low < high:
        middle = (low + high) // 2
        if (mask & ((1 << middle) - 1)).bit_count() > index:
            high = middle
        else:
            low = middle + 1
    return low - 1


def runoff(matrix, iterations=1000, seed=42):
    """Return wins and mean elimination rounds (first=1, winner=N).

    Rank buckets are precomputed once and represented as integer bitsets. The
    active bitset makes each elimination lookup and removal cheap while
    retaining the reference implementation's ascending active-county order
    for seeded tie selection.
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

    # Each factor is ordered from worst rank to best rank. A bucket is the
    # bitset of counties tied at one rank, so the first nonempty bucket is the
    # exact equivalent of max(matrix[i][factor] for i in active).
    factor_buckets = []
    county_bits = [1 << county for county in range(n)]
    for factor in range(m):
        order = sorted(range(n), key=lambda i: matrix[i][factor], reverse=True)
        buckets = []
        current_value = None
        for county in order:
            value = matrix[county][factor]
            if current_value != value:
                buckets.append(0)
                current_value = value
            buckets[-1] |= county_bits[county]
        factor_buckets.append(buckets)

    rng = random.Random(seed)
    wins, rounds = [0] * n, [0] * n
    all_active = (1 << n) - 1
    for _ in range(iterations):
        active = all_active
        first_nonempty_bucket = [0] * m
        factors = list(range(m))
        rng.shuffle(factors)
        for round_number in range(1, n):
            if not factors:
                factors.extend(range(m))
                rng.shuffle(factors)
            factor = factors.pop()
            buckets = factor_buckets[factor]
            bucket_index = first_nonempty_bucket[factor]
            while not (active & buckets[bucket_index]):
                bucket_index += 1
            first_nonempty_bucket[factor] = bucket_index
            candidates = active & buckets[bucket_index]
            candidate_count = candidates.bit_count()
            random_index = rng.randrange(candidate_count)
            if candidate_count == 1:
                loser = (candidates & -candidates).bit_length() - 1
            else:
                loser = _select_set_bit(candidates, random_index)
            rounds[loser] += round_number
            active &= ~county_bits[loser]
        winner = active.bit_length() - 1
        wins[winner] += 1
        rounds[winner] += n
    return wins, [v / iterations for v in rounds]
