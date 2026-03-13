"""Benchmark configuration and CLI argument parsing."""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field


_FOLDER_ID_PATTERN = re.compile(
    r"(?:https?://)?drive\.google\.com/drive/(?:u/\d+/)?folders/([A-Za-z0-9_-]+)"
)


def _extract_folder_id(url: str) -> str:
    """Extract a Google Drive folder ID from a URL or bare ID."""
    match = _FOLDER_ID_PATTERN.search(url)
    if match:
        return match.group(1)
    if "/" not in url and len(url) > 5:
        return url
    raise ValueError(f"Cannot parse Google Drive folder ID from: {url}")


@dataclass
class BenchmarkConfig:
    """All configuration for a benchmark run."""

    folder_id: str
    folder_url: str
    access_token: str
    openai_api_key: str
    model: str = "gpt-5.2"
    evaluator_model: str = "gpt-5.2"
    max_iterations: int = 15
    concurrency: int = 3
    max_retries: int = 3
    retry_base_sec: float = 5.0
    question_timeout_sec: float = 300.0
    qa_file: str = "benchmark/qa_test.json"
    results_path: str = ""
    question_filter: list[str] | None = None
    difficulty_filter: str | None = None
    resume_path: str | None = None
    user_email: str | None = None


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the benchmark runner."""
    parser = argparse.ArgumentParser(
        description="Run benchmark questions against the FolderAgent"
    )
    parser.add_argument(
        "--folder-url",
        help="Google Drive folder URL or bare folder ID",
    )
    parser.add_argument(
        "--questions",
        nargs="+",
        help="Run only these question IDs (e.g. E1 M3 H2)",
    )
    parser.add_argument(
        "--difficulty",
        choices=["easy", "medium", "hard"],
        help="Run only questions of this difficulty",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=3,
        help="Number of concurrent questions (default: 3)",
    )
    parser.add_argument(
        "--model",
        default="gpt-5.2",
        help="Model for the agent (default: gpt-5.2)",
    )
    parser.add_argument(
        "--evaluator-model",
        default="gpt-5.2",
        help="Model for the evaluator (default: gpt-5.2)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=15,
        help="Max agent iterations per question (default: 15)",
    )
    parser.add_argument(
        "--access-token",
        help="Raw Google OAuth access token (bypasses DB lookup)",
    )
    parser.add_argument(
        "--user-email",
        help="Email for DB token lookup (default: first user)",
    )
    parser.add_argument(
        "--resume",
        help="Path to a results JSON file to resume",
    )
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Force a fresh run even if results exist",
    )
    parser.add_argument(
        "--qa-file",
        default="benchmark/qa_test.json",
        help="Path to the QA test JSON file",
    )
    parser.add_argument(
        "--results-dir",
        default="benchmark/results",
        help="Directory for results output",
    )
    return parser.parse_args(argv)
