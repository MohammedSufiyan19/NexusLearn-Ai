"""
NexusLearn AI — Retrieval Metrics (no LLM needed)
Hit@k, MRR, Page Recall@k — deterministic and free.
"""
import math


def hit_at_k(retrieved_pages: list[tuple[str, int]], gold_sources: list[dict], k: int = 5) -> float:
    """
    Returns 1.0 if any gold page appears in the top-k retrieved chunks, else 0.0.
    retrieved_pages: [(filename, page_number), ...]
    gold_sources: [{"file": "...", "pages": [1, 2]}, ...]
    """
    top_k = retrieved_pages[:k]
    for gs in gold_sources:
        for page in gs.get("pages", []):
            if (gs["file"], page) in top_k:
                return 1.0
    return 0.0


def reciprocal_rank(retrieved_pages: list[tuple[str, int]], gold_sources: list[dict]) -> float:
    """
    Mean Reciprocal Rank: 1/rank of first relevant result.
    """
    for rank, (fname, page) in enumerate(retrieved_pages, start=1):
        for gs in gold_sources:
            if fname == gs["file"] and page in gs.get("pages", []):
                return 1.0 / rank
    return 0.0


def page_recall_at_k(retrieved_pages: list[tuple[str, int]], gold_sources: list[dict], k: int = 5) -> float:
    """
    Fraction of gold pages found in top-k retrieved pages.
    """
    top_k = set(retrieved_pages[:k])
    gold_pages = set()
    for gs in gold_sources:
        for page in gs.get("pages", []):
            gold_pages.add((gs["file"], page))

    if not gold_pages:
        return 1.0  # unanswerable — no gold pages to find
    found = gold_pages & top_k
    return len(found) / len(gold_pages)


def compute_retrieval_metrics(results: list[dict], k: int = 5) -> dict:
    """
    Compute aggregate retrieval metrics over all eval results.

    Each result dict must have:
      - retrieved_pages: [(file, page), ...]
      - gold_sources: [{"file": ..., "pages": [...]}, ...]
      - type: str (to separate unanswerable)
    """
    answerable = [r for r in results if r.get("type") != "unanswerable"]
    unanswerable = [r for r in results if r.get("type") == "unanswerable"]

    hits, mrrs, recalls = [], [], []
    for r in answerable:
        pages = r.get("retrieved_pages", [])
        gold = r.get("gold_sources", [])
        hits.append(hit_at_k(pages, gold, k))
        mrrs.append(reciprocal_rank(pages, gold))
        recalls.append(page_recall_at_k(pages, gold, k))

    def _mean(lst):
        return sum(lst) / len(lst) if lst else 0.0

    def _std(lst):
        if len(lst) < 2:
            return 0.0
        m = _mean(lst)
        return math.sqrt(sum((x - m) ** 2 for x in lst) / (len(lst) - 1))

    return {
        "n_answerable": len(answerable),
        "n_unanswerable": len(unanswerable),
        f"Hit@{k}": f"{_mean(hits):.3f} ± {_std(hits):.3f}",
        "MRR": f"{_mean(mrrs):.3f} ± {_std(mrrs):.3f}",
        f"PageRecall@{k}": f"{_mean(recalls):.3f} ± {_std(recalls):.3f}",
    }


def print_table(metrics: dict, config_name: str = "Baseline"):
    """Print a markdown table row."""
    print(f"\n### {config_name}")
    print("| Metric | Value |")
    print("|--------|-------|")
    for k, v in metrics.items():
        print(f"| {k} | {v} |")
