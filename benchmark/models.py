"""Dataclasses for benchmark trace, evaluation, and results."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ToolCallTrace:
    """Record of a single tool invocation during an agent iteration."""

    name: str
    arguments: dict
    result_preview: str  # first 2000 chars
    result_length: int
    citations_produced: int
    duration_sec: float
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "arguments": self.arguments,
            "result_preview": self.result_preview,
            "result_length": self.result_length,
            "citations_produced": self.citations_produced,
            "duration_sec": round(self.duration_sec, 2),
            "error": self.error,
        }


@dataclass
class IterationTrace:
    """Record of a single agent iteration (LLM call + tool executions)."""

    iteration: int
    assistant_content: str | None
    tool_calls: list[ToolCallTrace]
    is_final: bool
    duration_sec: float

    def to_dict(self) -> dict:
        return {
            "iteration": self.iteration,
            "assistant_content": self.assistant_content,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
            "is_final": self.is_final,
            "duration_sec": round(self.duration_sec, 2),
        }


@dataclass
class AgentTrace:
    """Full trace of an agent run across all iterations."""

    iterations: list[IterationTrace]
    total_duration_sec: float
    total_llm_calls: int
    total_tool_calls: int
    hit_limit: bool

    def to_dict(self) -> dict:
        return {
            "iterations": [it.to_dict() for it in self.iterations],
            "total_duration_sec": round(self.total_duration_sec, 2),
            "total_llm_calls": self.total_llm_calls,
            "total_tool_calls": self.total_tool_calls,
            "hit_limit": self.hit_limit,
        }


@dataclass
class Evaluation:
    """Structured evaluation from the LLM judge."""

    verdict: str  # pass, partial, fail
    answer_score: int
    answer_reasoning: str
    source_score: int
    source_reasoning: str
    missing_facts: list[str]
    hallucinated_facts: list[str]
    expected_sources: list[str]
    found_sources: list[str]
    missed_sources: list[str]
    extra_sources: list[str]

    def to_dict(self) -> dict:
        return {
            "verdict": self.verdict,
            "answer_score": self.answer_score,
            "answer_reasoning": self.answer_reasoning,
            "source_score": self.source_score,
            "source_reasoning": self.source_reasoning,
            "missing_facts": self.missing_facts,
            "hallucinated_facts": self.hallucinated_facts,
            "expected_sources": self.expected_sources,
            "found_sources": self.found_sources,
            "missed_sources": self.missed_sources,
            "extra_sources": self.extra_sources,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Evaluation:
        return cls(**d)


@dataclass
class QuestionResult:
    """Result of running and evaluating a single question."""

    id: str
    difficulty: str
    persona: str
    department: str
    question: str
    expected_answer: str
    expected_sources: list[str]
    agent_answer: str | None = None
    agent_citations: list[dict] | None = None
    agent_iterations: int | None = None
    agent_hit_limit: bool | None = None
    duration_sec: float | None = None
    trace: AgentTrace | None = None
    evaluation: Evaluation | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "difficulty": self.difficulty,
            "persona": self.persona,
            "department": self.department,
            "question": self.question,
            "expected_answer": self.expected_answer,
            "expected_sources": self.expected_sources,
            "agent_answer": self.agent_answer,
            "agent_citations": self.agent_citations,
            "agent_iterations": self.agent_iterations,
            "agent_hit_limit": self.agent_hit_limit,
            "duration_sec": round(self.duration_sec, 2) if self.duration_sec else None,
            "trace": self.trace.to_dict() if self.trace else None,
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "error": self.error,
        }
        return d

    @classmethod
    def from_dict(cls, d: dict) -> QuestionResult:
        trace = None
        if d.get("trace"):
            t = d["trace"]
            iterations = []
            for it in t.get("iterations", []):
                tool_calls = [ToolCallTrace(**tc) for tc in it.get("tool_calls", [])]
                iterations.append(IterationTrace(
                    iteration=it["iteration"],
                    assistant_content=it.get("assistant_content"),
                    tool_calls=tool_calls,
                    is_final=it["is_final"],
                    duration_sec=it["duration_sec"],
                ))
            trace = AgentTrace(
                iterations=iterations,
                total_duration_sec=t["total_duration_sec"],
                total_llm_calls=t["total_llm_calls"],
                total_tool_calls=t["total_tool_calls"],
                hit_limit=t["hit_limit"],
            )
        evaluation = Evaluation.from_dict(d["evaluation"]) if d.get("evaluation") else None
        return cls(
            id=d["id"],
            difficulty=d["difficulty"],
            persona=d["persona"],
            department=d["department"],
            question=d["question"],
            expected_answer=d["expected_answer"],
            expected_sources=d["expected_sources"],
            agent_answer=d.get("agent_answer"),
            agent_citations=d.get("agent_citations"),
            agent_iterations=d.get("agent_iterations"),
            agent_hit_limit=d.get("agent_hit_limit"),
            duration_sec=d.get("duration_sec"),
            trace=trace,
            evaluation=evaluation,
            error=d.get("error"),
        )


@dataclass
class BenchmarkResults:
    """Container for a full benchmark run."""

    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    completed_at: str | None = None
    config: dict = field(default_factory=dict)
    summary: dict = field(default_factory=dict)
    results: list[QuestionResult] = field(default_factory=list)

    @property
    def completed_ids(self) -> set[str]:
        return {r.id for r in self.results}

    def add(self, result: QuestionResult) -> None:
        self.results.append(result)

    def finalize(self) -> None:
        self.completed_at = datetime.now(timezone.utc).isoformat()
        total = len(self.results)
        completed = sum(1 for r in self.results if r.error is None)
        passed = sum(1 for r in self.results if r.evaluation and r.evaluation.verdict == "pass")
        partial = sum(1 for r in self.results if r.evaluation and r.evaluation.verdict == "partial")
        failed = sum(1 for r in self.results if r.evaluation and r.evaluation.verdict == "fail")
        errors = sum(1 for r in self.results if r.error is not None)

        scored = [r for r in self.results if r.evaluation]
        avg_answer = sum(r.evaluation.answer_score for r in scored) / len(scored) if scored else 0
        avg_source = sum(r.evaluation.source_score for r in scored) / len(scored) if scored else 0

        with_iters = [r for r in self.results if r.agent_iterations is not None]
        avg_iters = sum(r.agent_iterations for r in with_iters) / len(with_iters) if with_iters else 0

        with_dur = [r for r in self.results if r.duration_sec is not None]
        avg_dur = sum(r.duration_sec for r in with_dur) / len(with_dur) if with_dur else 0
        total_dur = sum(r.duration_sec for r in with_dur) if with_dur else 0

        by_difficulty: dict[str, dict] = {}
        for diff in ("easy", "medium", "hard"):
            diff_results = [r for r in self.results if r.difficulty == diff]
            diff_scored = [r for r in diff_results if r.evaluation]
            diff_pass = sum(1 for r in diff_scored if r.evaluation.verdict == "pass")
            diff_avg = sum(r.evaluation.answer_score for r in diff_scored) / len(diff_scored) if diff_scored else 0
            by_difficulty[diff] = {
                "total": len(diff_results),
                "pass": diff_pass,
                "partial": sum(1 for r in diff_scored if r.evaluation.verdict == "partial"),
                "fail": sum(1 for r in diff_scored if r.evaluation.verdict == "fail"),
                "avg_score": round(diff_avg, 1),
            }

        self.summary = {
            "total": total,
            "completed": completed,
            "pass": passed,
            "partial": partial,
            "fail": failed,
            "error": errors,
            "pass_rate_pct": round(passed / total * 100, 1) if total else 0,
            "pass_partial_rate_pct": round((passed + partial) / total * 100, 1) if total else 0,
            "avg_answer_score": round(avg_answer, 1),
            "avg_source_score": round(avg_source, 1),
            "avg_iterations": round(avg_iters, 1),
            "avg_duration_sec": round(avg_dur, 1),
            "total_duration_sec": round(total_dur, 1),
            "by_difficulty": by_difficulty,
        }

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "config": self.config,
            "summary": self.summary,
            "results": [r.to_dict() for r in self.results],
        }

    @classmethod
    def from_dict(cls, d: dict) -> BenchmarkResults:
        results = [QuestionResult.from_dict(r) for r in d.get("results", [])]
        br = cls(
            run_id=d.get("run_id", str(uuid.uuid4())),
            started_at=d.get("started_at", ""),
            completed_at=d.get("completed_at"),
            config=d.get("config", {}),
            summary=d.get("summary", {}),
            results=results,
        )
        return br
