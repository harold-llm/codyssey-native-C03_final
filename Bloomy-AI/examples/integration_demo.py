"""Offline end-to-end demo with synthetic data and a simulated backend."""
import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
from tempfile import mkdtemp

from ai.agent import CoachAgent, CoachRequest, Feedback, LearningCard
from ai.agent.guardrails import AI_LABEL
from ai.contracts import RecommendationRequest
from ai.memory import MemoryConflictError, MemoryService
from ai.rag import RecommendationEngine
from ai.rag.ingest import load_catalog, validate_catalog

ROOT = Path(__file__).resolve().parents[1]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def demo_catalog():
    """Extend fictional samples only; do not mark any item as reviewed."""
    items = load_catalog(ROOT / "data" / "catalog" / "sample.json")
    for content_id, title, level, skill, kind in (
        ("integration-audio-l2", "통합 데모 듣기 오디오 L2", 2, "listening", "audio"),
        ("integration-audio-l1", "통합 데모 듣기 오디오 L1", 1, "listening", "audio"),
        ("integration-speaking-l2", "통합 데모 인사 오디오 L2", 2, "speaking", "audio"),
    ):
        item = deepcopy(items[0])
        item.update(id=content_id, title=title, level=level, skill=skill, type=kind,
                    link=f"https://example.org/bloomy-demo/{content_id}", review_status="unreviewed",
                    expert_note="통합 흐름 검증용 가상 자료입니다. 전문가 검수와 실제 교육 자료가 아닙니다.")
        if skill == "speaking":
            item.update(task="짧은 인사 소리를 듣고 몸짓이나 소리로 답해 보세요.",
                        check_point="인사 소리에 몸짓이나 소리로 반응하나요?")
        items.append(item)
    return validate_catalog(items)


class DemoBackend:
    """Demonstration only: approval and absolute card updates in a JSON file."""
    def __init__(self, plan, path):
        self.path = path
        self.state = {"simulation_only": True, "status": plan.status,
                      "cards": [dict(child_id=1, **day) for day in plan.days],
                      "processed_events": [], "pending": {}}
        self.save()

    def save(self):
        write_json(self.path, self.state)

    def card(self, index):
        return LearningCard(**deepcopy(self.state["cards"][index]))

    def approve_plan(self):
        if self.state["status"] != "draft":
            raise ValueError("only a draft can be approved")
        self.state["status"] = "approved"
        self.save()

    def accept(self, event_id, request, result):
        if event_id in self.state["processed_events"]:
            return False
        if self.state["status"] != "approved":
            raise ValueError("backend approval gate")
        original = asdict(request.next_card) if request.next_card else None
        target = next((c for c in self.state["cards"] if original and c["date"] == original["date"]), None)
        if target != original:
            raise ValueError("stale next-card snapshot")
        if result.adjust["requires_parent_approval"]:
            if result.adjust["auto_apply"] or result.tomorrow != original:
                raise ValueError("pending change cannot be auto-applied")
            self.state["pending"][event_id] = {"original": original,
                                              "proposal": result.adjust["proposal"], "status": "pending"}
        elif result.adjust["auto_apply"]:
            target.update(result.tomorrow)  # Absolute replacement; never subtract twice.
        self.state["processed_events"].append(event_id)
        self.save()
        return True

    def approve_change(self, event_id):
        pending = self.state["pending"][event_id]
        if self.state["status"] != "approved" or pending["status"] != "pending" or not pending["proposal"]:
            raise ValueError("no approvable change")
        target = next(c for c in self.state["cards"] if c["date"] == pending["original"]["date"])
        if target != pending["original"]:
            raise ValueError("proposal targets a stale card")
        target.update(pending["proposal"])
        pending["status"] = "approved_in_simulation"
        self.save()


def run_demo(run_dir=None):
    """Create a fresh dedicated run. Never reset or reuse an existing directory."""
    if run_dir is None:
        parent = ROOT / "data" / "local" / "integration-runs"
        parent.mkdir(parents=True, exist_ok=True)
        directory = Path(mkdtemp(prefix="run-", dir=parent))
    else:
        directory = Path(run_dir).resolve()
        directory.mkdir(parents=True, exist_ok=False)
    checks, scenarios = [], []

    def check(name, condition):
        checks.append({"name": name, "passed": bool(condition)})
        if not condition:
            raise RuntimeError(f"integration check failed: {name}")

    catalog_path = directory / "catalog.json"
    write_json(catalog_path, demo_catalog())
    db_path = directory / "memory.sqlite3"
    retained_request = retained_result = None
    with MemoryService.from_sqlite(db_path) as memory:
        memory.set_preferences(1, "2026-11-01", favorite_topics=["동물"], owned_materials=["demo-sound-001"])
        rag = RecommendationEngine.from_file(catalog_path, memory=memory)
        plan = rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-16"), child_id=1)
        write_json(directory / "initial-plan.json", plan.to_dict())
        backend = DemoBackend(plan, directory / "backend-state.json")
        check("rag_20_day_draft", plan.status == "draft" and len(plan.days) == 20)
        check("saved_owned_material_prioritized", plan.days[0]["content_id"] == "demo-sound-001")
        check("rag_evidence_grounded", {d["content_id"] for d in plan.days} <= {e["content_id"] for e in plan.evidence})

        # Read-only gate preview, without memory: do not persist feedback before activation.
        preview = CoachRequest(child_id=1, age=5, base_level=2, plan_status="draft",
                               feedback=Feedback(1, backend.card(0).date, "partial", 3, 3, 2),
                               today_card=backend.card(0), next_card=backend.card(1))
        gate = CoachAgent(RecommendationEngine(rag.catalog)).coach(preview)
        check("draft_gate_blocks_next_card", gate.tomorrow is None and not gate.adjust["auto_apply"])
        check("preview_has_no_persisted_feedback", not memory.get_context(1, "2026-11-16")["history"])
        backend.approve_plan()  # Explicit simulated parent action, not real authorization.
        check("simulated_parent_plan_approval", backend.state["status"] == "approved")
        agent = CoachAgent(rag)
        cases = [
            ("A_keep", "full", 4, 4, "", False, "A", "none"),
            ("B_shrink", "partial", 3, 2, "", False, "B", "shrink"),
            ("single_interest_dip", "full", 2, 4, "", False, "A", "none"),
            ("C_swap", "full", 2, 4, "", False, "C", "swap"),
            ("C_B_swap_easy", "full", 2, 2, "", False, "C", "swap_easy"),
            ("rest_day", "full", 1, 1, "무시할 메모", True, "SKIP", "none"),
            ("parent_change_request", "full", 4, 4, "다른 자료로 바꿔 주세요", False, "C", "propose_swap"),
            ("question_with_rag", "full", 4, 4, "어떻게 도와줄까요?", False, "C", "none"),
            ("expert_referral", "full", 4, 4, "발달 진단이 필요한가요?", False, "C", "none"),
            ("A_after_adjustments", "full", 4, 4, "", False, "A", "none"),
        ]
        for index, (name, completion, interest, comprehension, memo, rest, expected_case, expected_adjust) in enumerate(cases):
            today, next_card = backend.card(index), backend.card(index + 1)
            request = CoachRequest(child_id=1, age=5, base_level=2, plan_status=backend.state["status"],
                feedback=Feedback(1, today.date, completion, 4, interest, comprehension, memo, rest),
                today_card=today, next_card=next_card)
            event_id = f"demo:{name}"
            result = agent.coach(request, event_id=event_id)
            check(name + "_branch", (result.case, result.adjust["type"]) == (expected_case, expected_adjust))
            check(name + "_message", result.message is None if rest else result.message.endswith(AI_LABEL))
            check(name + "_no_unverified_confidence", result.confidence_sentence == "")
            backend.accept(event_id, request, result)
            if index == 1:
                retained_request, retained_result = request, result.to_dict()
                retry = agent.coach(request, event_id=event_id)
                check("same_event_returns_identical_result", retry.to_dict() == retained_result)
                check("backend_ignores_duplicate_application", not backend.accept(event_id, request, retry))
                check("shrink_absolute_minutes", backend.card(index + 1).minutes == 5)
            if name == "single_interest_dip":
                check("single_dip_flag", result.flags["interest_dip"])
            if name == "C_B_swap_easy":
                check("C_B_overlap_flag", result.flags["difficulty_adjust"])
            if name == "parent_change_request":
                check("parent_request_does_not_apply", backend.card(index + 1) == next_card and result.adjust["requires_parent_approval"])
                check("parent_change_has_grounded_candidate", result.adjust["proposal"] is not None)
                backend.approve_change(event_id)  # Explicit second simulated approval.
                check("only_simulated_approval_applies_proposal", asdict(backend.card(index + 1)) == result.adjust["proposal"])
            if name == "question_with_rag":
                check("question_has_catalog_advice", bool(result.evidence) and "자료 안내:" in result.message)
            if name == "expert_referral":
                check("expert_referral_flag", result.flags["expert_referral"])
            scenarios.append({"scenario": name, "event_id": event_id,
                              "request": json.loads(json.dumps(asdict(request), ensure_ascii=False)),
                              "result": result.to_dict(), "backend_next_card": asdict(backend.card(index + 1))})

        context = memory.get_context(1, "2026-11-27")
        check("ten_feedback_records_including_rest", len(context["history"]) == 10)
        check("rest_excluded_from_learning_count", context["summary"]["record_days"] == 9 and context["summary"]["rest_days"] == 1)
        past = memory.get_context(1, "2026-11-17")
        check("as_of_excludes_future_feedback", len(past["history"]) == 2)
        try:
            agent.coach(replace(retained_request, feedback=replace(retained_request.feedback, interest=1)), event_id="demo:B_shrink")
        except MemoryConflictError:
            conflict_detected = True
        else:
            conflict_detected = False
        check("conflicting_retry_rejected", conflict_detected)

        # A second synthetic child has independent learned content preferences.
        memory.set_preferences(2, "2026-11-01", favorite_topics=["우주"])
        for day in ("2026-11-16", "2026-11-17"):
            memory.record_feedback(Feedback(2, day, "full", 5, 5, 4), content_id="demo-speaking-001", minutes=10)
        child_two_plan = rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-30"), child_id=2)
        check("learned_response_changes_rag_order", child_two_plan.days[0]["content_id"] == "demo-speaking-001")
        check("children_are_isolated", memory.get_context(1, "2026-11-27") == context)
        next_plan = rag.recommend(RecommendationRequest(age=5, base_level=2, start_date="2026-11-30"), child_id=1)
        check("next_recommendation_reads_history", next_plan.memory_context["summary"]["record_days"] == 9)
        check("next_recommendation_still_requires_approval", next_plan.status == "draft")
        write_json(directory / "next-plan.json", next_plan.to_dict())

    # Close/reopen to demonstrate persistence and exact retry after process-style restart.
    with MemoryService.from_sqlite(db_path) as reopened:
        new_agent = CoachAgent(RecommendationEngine.from_file(catalog_path), memory=reopened)
        replay = new_agent.coach(retained_request, event_id="demo:B_shrink")
        check("reopened_db_returns_cached_result", replay.to_dict() == retained_result)
        check("reopened_db_keeps_ten_records", len(reopened.get_context(1, "2026-11-27")["history"]) == 10)
        # Delete a throwaway identity only; do not erase the demonstrated histories.
        reopened.record_feedback(Feedback(3, "2026-11-16", "full", 4, 4, 4))
        reopened.delete_child(3)
        check("delete_child_is_scoped", not reopened.get_context(3, "2026-11-27")["history"]
              and len(reopened.get_context(2, "2026-11-27")["history"]) == 2)

    report = {"demo_version": "bloomy-integration-v1", "status": "passed", "simulation_only": True,
              "api_key_required": False, "run_directory": str(directory), "database": str(db_path),
              "checks_passed": len(checks), "checks": checks,
              "primary_child_records": 10, "primary_child_learning_days": 9,
              "scenarios": scenarios, "final_memory": context,
              "limitations": ["가상 미검수 카탈로그", "부모 승인과 백엔드 카드 반영은 시뮬레이션",
                              "TF-IDF·규칙·템플릿 기반이며 LLM과 실제 HTTP 연동은 포함하지 않음"]}
    write_json(directory / "report.json", report)
    return report


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, help="New directory only; existing directories are never reused")
    args = parser.parse_args()
    report = run_demo(args.run_dir)
    print(json.dumps({key: report[key] for key in ("status", "checks_passed", "run_directory", "primary_child_records")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
