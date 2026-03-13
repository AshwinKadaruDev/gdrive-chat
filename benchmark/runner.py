"""Benchmark runner: TracingFolderAgent + orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import tempfile
import time
import uuid
from pathlib import Path

# Ensure project root + backend are on sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parent.parent)
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)
_BACKEND = str(Path(_PROJECT_ROOT) / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)

from app.services.agent import AgentResponse, FolderAgent, _LLM_ERRORS
from app.services.google_drive import GoogleDriveService
from app.services.llm import LLMClient
from app.services.llm.errors import LLMRateLimitError
from app.services.tool_executor import Citation, execute_tool

from benchmark.evaluator import evaluate_answer
from benchmark.models import (
    AgentTrace,
    BenchmarkResults,
    IterationTrace,
    QuestionResult,
    ToolCallTrace,
)

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

            # Call LLM with tools (retry on rate limit)
            response = None
            for llm_attempt in range(4):
                try:
                    response = await self.llm_client.call_with_tools(
                        messages=messages,
                        tools=self.tools,
                        model=self.model,
                    )
                    break
                except LLMRateLimitError as exc:
                    if llm_attempt < 3:
                        wait = 30 * (2 ** llm_attempt)  # 30s, 60s, 120s
                        logger.warning(
                            "Rate limited on iteration %d (attempt %d/4), waiting %ds",
                            iteration, llm_attempt + 1, wait,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error("Rate limit exceeded after 4 attempts on iteration %d", iteration)
                        iter_dur = time.monotonic() - iter_start
                        self.trace_iterations.append(IterationTrace(
                            iteration=iteration,
                            assistant_content=f"[RATE LIMITED: {exc}]",
                            tool_calls=[],
                            is_final=True,
                            duration_sec=iter_dur,
                        ))
                        return AgentResponse(
                            content="Rate limit exceeded. Please try again later.",
                            citations=all_citations,
                            iterations=iteration,
                            hit_limit=False,
                        )
                except _LLM_ERRORS as exc:
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

        # Hit max iterations — force a synthesis call
        logger.warning("TracingAgent hit max iterations (%d). Forcing synthesis.", self.max_iterations)
        messages.append({
            "role": "user",
            "content": (
                "You have reached the maximum number of steps. Based on everything "
                "you have read so far, provide your best answer now. Synthesize all "
                "the information you have gathered. Do not call any more tools."
            ),
        })
        final_content = ""
        try:
            synth_start = time.monotonic()
            response = await self.llm_client.call_with_tools(
                messages=messages, tools=[], model=self.model,
            )
            synth_dur = time.monotonic() - synth_start
            final_content = response.choices[0].message.content or ""
            self.trace_iterations.append(IterationTrace(
                iteration=self.max_iterations + 1,
                assistant_content=final_content,
                tool_calls=[],
                is_final=True,
                duration_sec=synth_dur,
            ))
        except Exception:
            logger.exception("Synthesis call failed after max iterations")

        # Fall back to last assistant content if synthesis failed
        if not final_content:
            for msg in reversed(messages):
                if msg.get("role") == "assistant" and msg.get("content"):
                    final_content = msg["content"]
                    break

        warning = (
            "\n\n**Note:** I reached my maximum number of reasoning steps. "
            "The answer above may be incomplete."
        )
        return AgentResponse(
            content=(final_content + warning) if final_content else (
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
    llm_client = LLMClient(
        openai_api_key=config.openai_api_key,
        anthropic_api_key=config.anthropic_api_key,
    )
    drive_service = GoogleDriveService()
    agent = TracingFolderAgent(
        llm_client=llm_client,
        drive_service=drive_service,
        model=config.model,
        max_iterations=config.max_iterations,
    )

    start = time.monotonic()
    timed_out = False
    try:
        response = await asyncio.wait_for(
            agent.answer(question, folder_id, access_token),
            timeout=config.question_timeout_sec,
        )
    except asyncio.TimeoutError:
        timed_out = True
        # Build partial response from whatever iterations completed
        content = ""
        for it in reversed(agent.trace_iterations):
            if it.assistant_content:
                content = it.assistant_content
                break
        response = AgentResponse(
            content=content or "Timed out before producing an answer.",
            citations=[],
            iterations=len(agent.trace_iterations),
            hit_limit=False,
        )

    total_time = time.monotonic() - start
    trace = AgentTrace(
        iterations=agent.trace_iterations,
        total_duration_sec=total_time,
        total_llm_calls=len(agent.trace_iterations),
        total_tool_calls=sum(len(it.tool_calls) for it in agent.trace_iterations),
        hit_limit=response.hit_limit,
        timed_out=timed_out,
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

                # Check for failure conditions before evaluation
                _base_result = dict(
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
                )

                if trace.timed_out:
                    return QuestionResult(**_base_result, error=f"Timed out after {config.question_timeout_sec}s")

                if agent_response.hit_limit:
                    return QuestionResult(**_base_result, error="Hit max iterations limit")

                _inability_tools = {"report_inability", "request_clarification"}
                _used_inability = any(
                    tc.name in _inability_tools
                    for it in trace.iterations
                    for tc in it.tool_calls
                )
                if _used_inability:
                    return QuestionResult(**_base_result, error="Agent could not answer the question")

                # Evaluate — wrap separately to preserve agent data on eval failure
                try:
                    evaluation = await evaluate_answer(
                        question=question,
                        agent_answer=agent_response.content,
                        agent_citations=citation_dicts,
                        config=config,
                    )
                except Exception as eval_err:
                    logger.exception("Evaluation failed for %s", qid)
                    return QuestionResult(**_base_result, error=f"Evaluation failed: {eval_err}")

                return QuestionResult(**_base_result, evaluation=evaluation)

            except asyncio.CancelledError:
                return QuestionResult(
                    id=qid,
                    difficulty=question["difficulty"],
                    persona=question["persona"],
                    department=question["department"],
                    question=question["question"],
                    expected_answer=question["expected_answer"],
                    expected_sources=question["sources"],
                    error="Cancelled",
                )

            except _LLM_ERRORS as e:
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


def _model_label(model: str) -> str:
    """Short model label for progress output."""
    if len(model) <= 10:
        return model
    # claude-opus-4-5-20251101 → opus-4.5
    for family in ("opus", "sonnet", "haiku"):
        idx = model.lower().find(family)
        if idx != -1:
            rest = model[idx + len(family):].lstrip("-").split("-")
            if len(rest) >= 2 and rest[0].isdigit() and rest[1].isdigit():
                return f"{family}-{rest[0]}.{rest[1]}"
            return family
    return model[:12]


def print_progress(
    result: QuestionResult, completed: int, total: int, model_prefix: str = "",
) -> None:
    """Print color-coded progress line for a completed question."""
    if result.error:
        color = _GRAY
        verdict = "ERROR"
        score = "-"
        iters = str(result.agent_iterations) if result.agent_iterations else "-"
        dur = f"{result.duration_sec:.1f}s" if result.duration_sec else "-"
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

    prefix = f"{model_prefix:<10} " if model_prefix else ""
    q_preview = result.question[:50] + ("..." if len(result.question) > 50 else "")
    print(
        f"[{prefix}{completed}/{total}] {result.id:<4} {color}{verdict:<8}{_RESET}"
        f"(score: {score}, {iters} iters, {dur})  {q_preview}"
    )


async def run_benchmark(
    questions: list[dict],
    config: BenchmarkConfig,
    model_prefix: str = "",
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
        results.config.pop("anthropic_api_key", None)

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

    try:
        for coro in asyncio.as_completed(tasks.keys()):
            result = await coro
            results.add(result)
            completed += 1
            save_results(config.results_path, results)
            print_progress(result, completed, total, model_prefix=model_prefix)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print(
            f"\n{_YELLOW}Interrupted — saving {len(results.results)}/{total} "
            f"results to {config.results_path}{_RESET}"
        )
        for task in tasks:
            if not task.done():
                task.cancel()

    results.finalize()
    save_results(config.results_path, results)
    return results


def _build_model_config(
    model: str, config: BenchmarkConfig, base_path: str,
) -> BenchmarkConfig:
    """Create a per-model BenchmarkConfig with its own results path."""
    is_claude = "claude" in model.lower()

    # Use explicit evaluator, or OpenAI for Claude agents (avoids sharing rate limit)
    if config.evaluator_model:
        evaluator = config.evaluator_model
    elif is_claude:
        evaluator = "gpt-5.2"
    else:
        evaluator = model

    # Cap Claude concurrency at 2 due to 30k tokens/min rate limit
    concurrency = min(config.concurrency, 2) if is_claude else config.concurrency

    model_config = BenchmarkConfig(
        folder_id=config.folder_id,
        folder_url=config.folder_url,
        access_token=config.access_token,
        openai_api_key=config.openai_api_key,
        anthropic_api_key=config.anthropic_api_key,
        model=model,
        evaluator_model=evaluator,
        max_iterations=config.max_iterations,
        concurrency=concurrency,
        max_retries=config.max_retries,
        retry_base_sec=config.retry_base_sec,
        question_timeout_sec=config.question_timeout_sec,
        qa_file=config.qa_file,
        question_filter=config.question_filter,
        difficulty_filter=config.difficulty_filter,
        resume_path=config.resume_path,
        user_email=config.user_email,
    )
    base_dir = os.path.dirname(base_path)
    base_name = os.path.splitext(os.path.basename(base_path))[0]
    model_slug = model.replace("/", "-")
    model_config.results_path = os.path.join(base_dir, f"{base_name}_{model_slug}.json")
    return model_config


async def run_all_models(
    questions: list[dict],
    config: BenchmarkConfig,
) -> list[BenchmarkResults]:
    """Run benchmarks across multiple models concurrently.

    Each model gets its own concurrency pool and results file.
    Models run in parallel since they hit separate API rate limits.
    """
    base_path = config.results_path
    group_id = str(uuid.uuid4())

    async def _run_model(model: str) -> BenchmarkResults:
        model_config = _build_model_config(model, config, base_path)
        label = _model_label(model)
        results = await run_benchmark(questions, model_config, model_prefix=label)
        results.model = model
        results.run_group = group_id
        save_results(model_config.results_path, results)
        return results

    # Launch all models concurrently
    tasks = [
        asyncio.create_task(_run_model(model))
        for model in config.models
    ]

    all_results: list[BenchmarkResults] = []
    try:
        for coro in asyncio.as_completed(tasks):
            result = await coro
            all_results.append(result)
    except (asyncio.CancelledError, KeyboardInterrupt):
        print(f"\n{_YELLOW}Interrupted — collecting completed model results...{_RESET}")
        for task in tasks:
            if task.done() and not task.cancelled():
                try:
                    all_results.append(task.result())
                except Exception:
                    pass
            elif not task.done():
                task.cancel()

    return all_results
