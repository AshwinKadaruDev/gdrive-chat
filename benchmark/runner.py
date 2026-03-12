"""Benchmark runner: TracingFolderAgent + orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING

# Ensure project root + backend are on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_BACKEND = str(Path(_PROJECT_ROOT) / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

import httpx
import openai

from app.services.agent import AgentResponse, FolderAgent
from app.services.google_drive import GoogleDriveService
from app.services.llm import LLMClient
from app.services.tool_executor import Citation, execute_tool

from benchmark.evaluator import evaluate_answer
from benchmark.models import (
    AgentTrace,
    BenchmarkResults,
    IterationTrace,
    QuestionResult,
    ToolCallTrace,
)

if TYPE_CHECKING:
    from benchmark.config import BenchmarkConfig

logger = logging.getLogger(__name__)

# ANSI colors for terminal output
_GREEN = "\033[92m"
_YELLOW = "\033[93m"
_RED = "\033[91m"
_GRAY = "\033[90m"
_RESET = "\033[0m"
_BOLD = "\033[1m"


class TracingFolderAgent(FolderAgent):
    """FolderAgent subclass that captures a full execution trace."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.trace_iterations: list[IterationTrace] = []

    async def answer(
        self,
        question: str,
        project_id: str,
        user_access_token: str,
        chat_history: list[dict] | None = None,
        session_id: str | None = None,
    ) -> AgentResponse:
        """Run the ReAct loop with trace instrumentation.

        This duplicates the loop from FolderAgent.answer() (agent.py:130-275)
        but adds timing and trace collection at each step.
        """
        self.trace_iterations = []

        messages: list[dict] = [{"role": "system", "content": self.system_prompt}]
        if chat_history:
            for msg in chat_history:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": question})

        all_citations: list[Citation] = []

        for iteration in range(1, self.max_iterations + 1):
            iter_start = time.monotonic()
            logger.info("TracingAgent iteration %d/%d", iteration, self.max_iterations)

            # Call LLM with tools
            try:
                response = await self.llm_client.call_with_tools(
                    messages=messages,
                    tools=self.tools,
                    model=self.model,
                )
            except (
                openai.RateLimitError,
                openai.APIStatusError,
                openai.APIConnectionError,
                openai.APITimeoutError,
                httpx.HTTPError,
            ) as exc:
                logger.error("LLM call failed on iteration %d: %s", iteration, exc)
                iter_dur = time.monotonic() - iter_start
                self.trace_iterations.append(IterationTrace(
                    iteration=iteration,
                    assistant_content=f"[LLM ERROR: {type(exc).__name__}: {exc}]",
                    tool_calls=[],
                    is_final=True,
                    duration_sec=iter_dur,
                ))
                return AgentResponse(
                    content="I'm sorry, something went wrong while processing your request. Please try again.",
                    citations=all_citations,
                    iterations=iteration,
                    hit_limit=False,
                )

            choice = response.choices[0]
            assistant_message = choice.message
            assistant_content = assistant_message.content

            if assistant_content:
                messages.append({"role": "assistant", "content": assistant_content})

            # Final answer — no tool calls
            if not assistant_message.tool_calls:
                iter_dur = time.monotonic() - iter_start
                self.trace_iterations.append(IterationTrace(
                    iteration=iteration,
                    assistant_content=assistant_content,
                    tool_calls=[],
                    is_final=True,
                    duration_sec=iter_dur,
                ))
                return AgentResponse(
                    content=assistant_content or "",
                    citations=all_citations,
                    iterations=iteration,
                    hit_limit=False,
                )

            # Tool calls — process them
            if assistant_content and assistant_message.tool_calls:
                messages.pop()

            tool_call_records = []
            for tc in assistant_message.tool_calls:
                tool_call_records.append({
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                })
            messages.append({
                "role": "assistant",
                "content": assistant_content,
                "tool_calls": tool_call_records,
                "_raw_output_items": assistant_message._raw_output_items,
            })

            # Execute each tool and collect traces
            tool_traces: list[ToolCallTrace] = []
            for tc in assistant_message.tool_calls:
                tool_name = tc.function.name
                try:
                    tool_args = json.loads(tc.function.arguments)
                except json.JSONDecodeError:
                    logger.warning("Malformed JSON in tool args for %s", tool_name)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": f"Invalid JSON in tool arguments: {tc.function.arguments}. Please provide valid JSON.",
                    })
                    tool_traces.append(ToolCallTrace(
                        name=tool_name,
                        arguments={},
                        result_preview="[Malformed JSON arguments]",
                        result_length=0,
                        citations_produced=0,
                        duration_sec=0,
                        error=f"Malformed JSON: {tc.function.arguments[:200]}",
                    ))
                    continue

                tool_start = time.monotonic()
                result_str, citations = await execute_tool(
                    tool_name=tool_name,
                    tool_args=tool_args,
                    project_id=project_id,
                    access_token=user_access_token,
                    drive_service=self.drive_service,
                    tool_cache=self.tool_cache,
                )
                tool_dur = time.monotonic() - tool_start

                all_citations.extend(citations)

                tool_traces.append(ToolCallTrace(
                    name=tool_name,
                    arguments=tool_args,
                    result_preview=result_str[:2000],
                    result_length=len(result_str),
                    citations_produced=len(citations),
                    duration_sec=tool_dur,
                ))

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_str,
                })

            iter_dur = time.monotonic() - iter_start
            self.trace_iterations.append(IterationTrace(
                iteration=iteration,
                assistant_content=assistant_content,
                tool_calls=tool_traces,
                is_final=False,
                duration_sec=iter_dur,
            ))

        # Hit max iterations
        logger.warning("TracingAgent hit max iterations (%d)", self.max_iterations)
        last_content = ""
        for msg in reversed(messages):
            if msg.get("role") == "assistant" and msg.get("content"):
                last_content = msg["content"]
                break
        warning = (
            "\n\n**Note:** I reached my maximum number of reasoning steps. "
            "The answer above may be incomplete."
        )
        return AgentResponse(
            content=(last_content + warning) if last_content else (
                "I was unable to formulate a complete answer within the allowed "
                "number of reasoning steps."
            ),
            citations=all_citations,
            iterations=self.max_iterations,
            hit_limit=True,
        )


async def run_agent_traced(
    question: str,
    folder_id: str,
    access_token: str,
    config: BenchmarkConfig,
) -> tuple[AgentResponse, AgentTrace]:
    """Create a fresh agent and run the question with tracing."""
    llm_client = LLMClient(openai_api_key=config.openai_api_key)
    drive_service = GoogleDriveService()
    agent = TracingFolderAgent(
        llm_client=llm_client,
        drive_service=drive_service,
        model=config.model,
        max_iterations=config.max_iterations,
    )

    start = time.monotonic()
    response = await asyncio.wait_for(
        agent.answer(question, folder_id, access_token),
        timeout=config.question_timeout_sec,
    )
    total_time = time.monotonic() - start

    trace = AgentTrace(
        iterations=agent.trace_iterations,
        total_duration_sec=total_time,
        total_llm_calls=len(agent.trace_iterations),
        total_tool_calls=sum(len(it.tool_calls) for it in agent.trace_iterations),
        hit_limit=response.hit_limit,
    )
    return response, trace


def _citation_to_dict(c: Citation) -> dict:
    return {
        "chunk_id": c.chunk_id,
        "file_id": c.file_id,
        "file_name": c.file_name,
        "source_url": c.source_url,
        "location": c.location,
        "snippet": c.snippet,
    }


async def run_single(
    question: dict,
    semaphore: asyncio.Semaphore,
    config: BenchmarkConfig,
) -> QuestionResult:
    """Run a single question: agent + evaluator, with retry logic."""
    qid = question["id"]

    async with semaphore:
        for attempt in range(config.max_retries):
            try:
                agent_response, trace = await run_agent_traced(
                    question=question["question"],
                    folder_id=config.folder_id,
                    access_token=config.access_token,
                    config=config,
                )

                # Serialize citations
                citation_dicts = [_citation_to_dict(c) for c in agent_response.citations]

                # Evaluate
                evaluation = await evaluate_answer(
                    question=question,
                    agent_answer=agent_response.content,
                    agent_citations=citation_dicts,
                    config=config,
                )

                return QuestionResult(
                    id=qid,
                    difficulty=question["difficulty"],
                    persona=question["persona"],
                    department=question["department"],
                    question=question["question"],
                    expected_answer=question["expected_answer"],
                    expected_sources=question["sources"],
                    agent_answer=agent_response.content,
                    agent_citations=citation_dicts,
                    agent_iterations=agent_response.iterations,
                    agent_hit_limit=agent_response.hit_limit,
                    duration_sec=trace.total_duration_sec,
                    trace=trace,
                    evaluation=evaluation,
                )

            except asyncio.TimeoutError:
                return QuestionResult(
                    id=qid,
                    difficulty=question["difficulty"],
                    persona=question["persona"],
                    department=question["department"],
                    question=question["question"],
                    expected_answer=question["expected_answer"],
                    expected_sources=question["sources"],
                    error=f"Timed out after {config.question_timeout_sec}s",
                )

            except (openai.RateLimitError, openai.APIConnectionError) as e:
                if attempt < config.max_retries - 1:
                    wait = config.retry_base_sec * (3 ** attempt)
                    logger.warning("Retrying %s in %.0fs: %s", qid, wait, e)
                    await asyncio.sleep(wait)
                else:
                    return QuestionResult(
                        id=qid,
                        difficulty=question["difficulty"],
                        persona=question["persona"],
                        department=question["department"],
                        question=question["question"],
                        expected_answer=question["expected_answer"],
                        expected_sources=question["sources"],
                        error=f"Failed after {config.max_retries} retries: {e}",
                    )

            except Exception as e:
                logger.exception("Unexpected error on %s", qid)
                return QuestionResult(
                    id=qid,
                    difficulty=question["difficulty"],
                    persona=question["persona"],
                    department=question["department"],
                    question=question["question"],
                    expected_answer=question["expected_answer"],
                    expected_sources=question["sources"],
                    error=f"{type(e).__name__}: {e}",
                )

    # Should not reach here, but just in case
    return QuestionResult(
        id=qid,
        difficulty=question["difficulty"],
        persona=question["persona"],
        department=question["department"],
        question=question["question"],
        expected_answer=question["expected_answer"],
        expected_sources=question["sources"],
        error="Unknown error",
    )


def save_results(path: str, results: BenchmarkResults) -> None:
    """Atomically save results to JSON file."""
    data = json.dumps(results.to_dict(), indent=2, ensure_ascii=False)
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(data)
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def print_progress(result: QuestionResult, completed: int, total: int) -> None:
    """Print color-coded progress line for a completed question."""
    if result.error:
        color = _GRAY
        verdict = "ERROR"
        score = "-"
        iters = "-"
        dur = "-"
    elif result.evaluation:
        v = result.evaluation.verdict
        color = _GREEN if v == "pass" else (_YELLOW if v == "partial" else _RED)
        verdict = v.upper()
        score = str(result.evaluation.answer_score)
        iters = str(result.agent_iterations)
        dur = f"{result.duration_sec:.1f}s"
    else:
        color = _GRAY
        verdict = "NO EVAL"
        score = "-"
        iters = str(result.agent_iterations or "-")
        dur = f"{result.duration_sec:.1f}s" if result.duration_sec else "-"

    q_preview = result.question[:50] + ("..." if len(result.question) > 50 else "")
    print(
        f"[{completed}/{total}] {result.id:<4} {color}{verdict:<8}{_RESET}"
        f"(score: {score}, {iters} iters, {dur})  {q_preview}"
    )


async def run_benchmark(
    questions: list[dict],
    config: BenchmarkConfig,
) -> BenchmarkResults:
    """Run the full benchmark: all questions with concurrency and incremental save."""
    # Load or create results
    if config.resume_path and os.path.exists(config.resume_path):
        with open(config.resume_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        results = BenchmarkResults.from_dict(data)
        print(f"Resuming from {config.resume_path} ({len(results.results)} completed)")
    else:
        results = BenchmarkResults(config=config.__dict__.copy())
        # Remove non-serializable fields from config
        results.config.pop("access_token", None)
        results.config.pop("openai_api_key", None)

    # Filter to pending questions
    pending = [q for q in questions if q["id"] not in results.completed_ids]
    if not pending:
        print("All questions already completed.")
        results.finalize()
        return results

    total = len(questions)
    completed = len(results.results)

    semaphore = asyncio.Semaphore(config.concurrency)

    # Create tasks
    tasks = {
        asyncio.create_task(run_single(q, semaphore, config)): q["id"]
        for q in pending
    }

    for coro in asyncio.as_completed(tasks.keys()):
        result = await coro
        results.add(result)
        completed += 1
        save_results(config.results_path, results)
        print_progress(result, completed, total)

    results.finalize()
    save_results(config.results_path, results)
    return results
