"""CLI entry point for the benchmark suite."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Ensure project root + backend are on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, str(Path(_PROJECT_ROOT) / "backend"))

from benchmark.auth import resolve_access_token
from benchmark.config import BenchmarkConfig, _extract_folder_id, parse_args
from benchmark.runner import run_benchmark, save_results


def _load_questions(qa_file: str) -> list[dict]:
    """Load and return the questions list from the QA JSON file."""
    # Try relative to project root first
    project_root = Path(__file__).resolve().parent.parent
    path = project_root / qa_file
    if not path.exists():
        path = Path(qa_file)
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["questions"]


def _filter_questions(
    questions: list[dict],
    question_ids: list[str] | None,
    difficulty: str | None,
) -> list[dict]:
    """Filter questions by ID and/or difficulty."""
    filtered = questions
    if question_ids:
        id_set = {qid.upper() for qid in question_ids}
        filtered = [q for q in filtered if q["id"].upper() in id_set]
    if difficulty:
        filtered = [q for q in filtered if q["difficulty"] == difficulty]
    return filtered


def _print_summary(results) -> None:
    """Print the final summary table."""
    s = results.summary
    if not s:
        return

    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("-" * 60)
    print(
        f"Total:    {s['total']} | "
        f"Pass: {s['pass']} | "
        f"Partial: {s['partial']} | "
        f"Fail: {s['fail']} | "
        f"Error: {s['error']}"
    )
    print(
        f"Pass Rate: {s['pass_rate_pct']}% | "
        f"Pass+Partial: {s['pass_partial_rate_pct']}%"
    )

    by_diff = s.get("by_difficulty", {})
    if by_diff:
        print()
        print("By Difficulty:")
        for diff in ("easy", "medium", "hard"):
            d = by_diff.get(diff, {})
            total_d = d.get("total", 0)
            pass_d = d.get("pass", 0)
            pct = f"{pass_d}/{total_d}" if total_d else "0/0"
            rate = f"({pass_d/total_d*100:.0f}%)" if total_d else "(0%)"
            avg = d.get("avg_score", 0)
            print(f"  {diff.capitalize():<8} {pct:>5}  {rate:>6}  avg score: {avg}")

    total_dur = s.get("total_duration_sec", 0)
    minutes = int(total_dur // 60)
    seconds = int(total_dur % 60)
    print()
    print(
        f"Avg iterations: {s.get('avg_iterations', 0)} | "
        f"Avg time: {s.get('avg_duration_sec', 0)}s | "
        f"Total: {minutes}m {seconds}s"
    )
    print(f"Results: {results.config.get('results_path', 'N/A')}")
    print("=" * 60)


async def main() -> int:
    args = parse_args()

    # Load questions
    all_questions = _load_questions(args.qa_file)
    questions = _filter_questions(all_questions, args.questions, args.difficulty)

    if not questions:
        print("No questions matched the filter criteria.")
        return 1

    # Resolve access token
    try:
        access_token = await resolve_access_token(args.access_token, args.user_email)
    except Exception as e:
        print(f"Error resolving access token: {e}")
        return 1

    # Resolve folder URL — prompt interactively if not provided
    folder_url = args.folder_url
    if not folder_url and args.resume:
        with open(args.resume, "r", encoding="utf-8") as f:
            resume_data = json.load(f)
        folder_url = resume_data.get("config", {}).get("folder_url", "")

    if not folder_url:
        print()
        folder_url = input("Google Drive folder URL: ").strip()
        if not folder_url:
            print("No URL provided.")
            return 1
        print()

    try:
        folder_id = _extract_folder_id(folder_url)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    # Get OpenAI API key from settings
    from app.dependencies import get_settings
    settings = get_settings()
    openai_api_key = settings.OPENAI_API_KEY

    # Generate results path
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%S")
    results_path = os.path.join(args.results_dir, f"{timestamp}.json")
    os.makedirs(os.path.dirname(results_path), exist_ok=True)

    # Build config
    config = BenchmarkConfig(
        folder_id=folder_id,
        folder_url=folder_url,
        access_token=access_token,
        openai_api_key=openai_api_key,
        model=args.model,
        evaluator_model=args.evaluator_model,
        max_iterations=args.max_iterations,
        concurrency=args.concurrency,
        results_path=results_path,
        question_filter=args.questions,
        difficulty_filter=args.difficulty,
        resume_path=args.resume if not args.fresh else None,
        user_email=args.user_email,
    )

    # If resuming, override results path
    if args.resume and not args.fresh:
        config.results_path = args.resume

    # Print header
    q_label = f"{len(questions)} questions"
    if args.questions:
        q_label += f" (filtered: {', '.join(args.questions)})"
    elif args.difficulty:
        q_label += f" (difficulty: {args.difficulty})"

    print(f"Benchmark: {q_label} | concurrency: {config.concurrency} | model: {config.model}")
    print("-" * 60)
    print()

    # Run
    results = await run_benchmark(questions, config)

    # Print summary
    _print_summary(results)

    # Exit code
    has_failures = any(
        r.error or (r.evaluation and r.evaluation.verdict == "fail")
        for r in results.results
    )
    return 1 if has_failures else 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
