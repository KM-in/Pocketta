"""Offline warm candidate-scoring benchmark; no provider calls or user data."""

import json
import platform
import statistics
import time

import numpy as np

from ..services.summary_index import VectorCache


def benchmark(count=10_000, dimensions=1536):
    vector = np.random.default_rng(42).standard_normal(dimensions).tolist()
    encoded = json.dumps(vector)
    rows = [
        {"id": str(i), "embedding_model": "synthetic", "embedding_json": encoded}
        for i in range(count)
    ]
    cache = VectorCache()
    start = time.perf_counter()
    cache.score("benchmark", rows, vector, "synthetic")
    cold = time.perf_counter() - start
    timings = []
    for _ in range(10):
        start = time.perf_counter()
        scores = cache.score("benchmark", rows, vector, "synthetic")
        sorted(scores, key=scores.get, reverse=True)[:40]
        timings.append(time.perf_counter() - start)
    return {
        "chunks": count,
        "dimensions": dimensions,
        "cold_seconds": cold,
        "warm_median_seconds": statistics.median(timings),
        "warm_p95_seconds": sorted(timings)[-1],
        "hardware": {
            "os": platform.platform(),
            "cpu": platform.processor(),
            "python": platform.python_version(),
        },
        "scope": "Synthetic exact vector scoring plus top-40 ranking; excludes SQL reads, network and generation",
    }


if __name__ == "__main__":
    print(json.dumps(benchmark(), indent=2))
