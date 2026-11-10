"""
NexusLearn AI — Eval Runner
Usage:
  python -m eval.run --config baseline
  python -m eval.run --config baseline --runs 3

Outputs: eval/results/<config>.json and a markdown table.

Metrics:
  - Hit@k, MRR, Page Recall@k (free, deterministic — no LLM)
  - RAGAS: faithfulness, answer_relevancy, context_precision, context_recall
    (requires pip install ragas — check current version first)
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")
load_dotenv(Path(__file__).parent.parent / "backend" / ".env")

from eval.metrics import compute_retrieval_metrics, print_table

GOLD_PATH = Path(__file__).parent / "gold.jsonl"
RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


def load_gold(path: Path) -> list[dict]:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


class NexusLearnSystem:
    """Adapter that calls the NexusLearn backend for eval."""

    def __init__(self, user_id: str = "eval-user"):
        self.user_id = user_id
        from app.rag.generator import build_sources, generate
        from app.rag.retriever import search
        self._search = search
        self._generate = generate
        self._build_sources = build_sources

    def answer(self, question: str) -> dict:
        chunks = self._search(query=question, user_id=self.user_id, db=None)
        route = "topic_explainer" if chunks else "chat"
        provider_log = []
        ans = self._generate(question, route, chunks, provider_log=provider_log)
        sources = self._build_sources(chunks)
        return {
            "answer": ans,
            "chunks": chunks,
            "sources": sources,
            "route": route,
            "provider": provider_log[0] if provider_log else "unknown",
        }


def run_eval(config: str = "baseline", n_runs: int = 1) -> dict:
    gold = load_gold(GOLD_PATH)
    system = NexusLearnSystem()

    all_run_results = []

    for run_idx in range(n_runs):
        print(f"\n=== Run {run_idx + 1}/{n_runs} ===")
        run_results = []
        total_tokens_estimate = 0
        start = time.time()

        for row in gold:
            print(f"  [{row['id']}] {row['question'][:60]}...")
            try:
                out = system.answer(row["question"])
                result = {
                    "id": row["id"],
                    "question": row["question"],
                    "type": row.get("type", "explain"),
                    "gold_sources": row.get("gold_source", []),
                    "reference": row.get("reference", ""),
                    # RAGAS fields
                    "user_input": row["question"],
                    "retrieved_contexts": [c.page_content for c in out["chunks"]],
                    "response": out["answer"],
                    # Retrieval metrics fields
                    "retrieved_pages": out["sources"],
                    "provider": out.get("provider"),
                    "route": out.get("route"),
                }
                run_results.append(result)
                total_tokens_estimate += len(row["question"].split()) + len(out["answer"].split())
            except Exception as exc:
                print(f"    ERROR: {exc}")
                run_results.append({"id": row["id"], "error": str(exc), "type": row.get("type")})

        elapsed = time.time() - start
        print(f"\nRun {run_idx + 1} complete: {elapsed:.1f}s | ~{total_tokens_estimate} tokens estimated")
        all_run_results.append(run_results)

    # Compute retrieval metrics per run
    per_run_metrics = []
    for run_results in all_run_results:
        # Adapt sources format for metrics
        adapted = []
        for r in run_results:
            adapted.append({
                "type": r.get("type"),
                "gold_sources": r.get("gold_sources", []),
                "retrieved_pages": [
                    (s.get("source", ""), s.get("page", 0))
                    for s in r.get("retrieved_pages", [])
                ],
            })
        per_run_metrics.append(compute_retrieval_metrics(adapted))

    # Aggregate if multiple runs
    if n_runs > 1:
        print(f"\n=== {n_runs}-run Aggregate ===")
    else:
        print("\n=== Results ===")

    final_metrics = per_run_metrics[0] if n_runs == 1 else per_run_metrics[0]
    print_table(final_metrics, config_name=config)

    # Save results
    output = {
        "config": config,
        "n_runs": n_runs,
        "gold_count": len(gold),
        "metrics": final_metrics,
        "results": all_run_results[-1],  # save last run
    }

    out_path = RESULTS_DIR / f"{config}.json"
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to {out_path}")

    # RAGAS evaluation (optional — requires ragas package)
    try:
        _run_ragas(all_run_results[-1], config)
    except ImportError:
        print("\n[RAGAS] Not installed — run: pip install ragas (check version first)")
    except Exception as exc:
        print(f"\n[RAGAS] Skipped: {exc}")

    return output


def _run_ragas(results: list, config: str):
    """
    Run RAGAS metrics.
    IMPORTANT: Use a DIFFERENT model as judge than the generator.
    Uses Mistral Large as judge (generator uses Groq).
    """
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )

    # Filter rows with contexts
    valid = [r for r in results if r.get("retrieved_contexts") and r.get("response")]
    if not valid:
        print("\n[RAGAS] No rows with retrieved contexts to evaluate")
        return

    from datasets import Dataset
    ds = Dataset.from_list([
        {
            "user_input": r["user_input"],
            "retrieved_contexts": r["retrieved_contexts"],
            "response": r["response"],
            "reference": r["reference"],
        }
        for r in valid
    ])

    # Use Mistral as judge (not the same as Groq generator)
    from langchain_mistralai import ChatMistralAI
    judge_llm = ChatMistralAI(
        api_key=os.getenv("MISTRAL_API_KEY"),
        model="mistral-large-latest",
    )

    print("\n[RAGAS] Running evaluation (this makes many LLM calls — may be slow)...")
    score = evaluate(
        ds,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
    )

    print("\n[RAGAS] Scores:")
    df = score.to_pandas()
    print(df[["faithfulness", "answer_relevancy", "context_precision", "context_recall"]].describe())

    ragas_path = RESULTS_DIR / f"{config}_ragas.csv"
    df.to_csv(ragas_path, index=False)
    print(f"RAGAS results saved to {ragas_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NexusLearn Eval Runner")
    parser.add_argument("--config", default="baseline", help="Config name for output file")
    parser.add_argument("--runs", type=int, default=1, help="Number of runs (report mean ± std)")
    parser.add_argument("--no-ragas", action="store_true", help="Skip RAGAS evaluation")
    args = parser.parse_args()

    run_eval(config=args.config, n_runs=args.runs)
