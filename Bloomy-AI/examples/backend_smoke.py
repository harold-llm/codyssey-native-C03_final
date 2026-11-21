# pyright: reportGeneralTypeIssues=false, reportIndexIssue=false, reportOptionalSubscript=false, reportOperatorIssue=false, reportCallIssue=false, reportArgumentType=false, reportAssignmentType=false, reportAttributeAccessIssue=false, reportUnknownParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportMissingParameterType=false, reportUnusedCallResult=false, reportAny=false
"""Exercise the local team checkout with a throwaway SQLite DB and demo catalog."""
import argparse
import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from ai.agent import CoachAgent
from ai.backend_adapter import coaching_request, recommendation_request, shared_catalog
from ai.rag import RecommendationEngine

from examples.ai_demo import demo_engine


def verify():
    import catalog

    import main
    import store

    def call(method, path, expected, body=None, token=None):
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        status, result, _ = main.dispatch(method, path, headers, body)
        if status != expected:
            raise RuntimeError(f"{method} {path}: expected {expected}, got {status}: {result}")
        return result

    samples = demo_engine().catalog
    catalog.load()
    if shared_catalog(catalog.search(), samples):
        raise RuntimeError("Expected a clean backend checkout without demo IDs")
    for item in samples:
        catalog.upsert_item(catalog.normalize(item))
    catalog.load()
    rag = RecommendationEngine(shared_catalog(catalog.search(), samples))
    coach = CoachAgent(rag)
    parent = call("POST", "/api/register", 201, {"email": "demo@example.org", "password": "demo-only-password"})
    token = parent["token"]
    today = date.today()
    monday = today - timedelta(days=today.weekday() + 7)
    levels = []
    for age, exposure, goal, answers, expected_level in (
        (5, "none", "듣기", "none", 1),
        (7, "some", "파닉스", "some", 3),
    ):
        created = call("POST", "/api/children", 201, {
            "name": f"시연 {age}세", "age": age, "exposure": exposure, "session_length": 15,
            "diagnosis": {key: answers for key in ("alphabet", "phonics", "readers", "response", "focus")},
        }, token)
        child = created["child"]
        child_id = child["id"]
        path = f"/api/children/{child_id}"
        request = recommendation_request(child, monday.isoformat(), goal=goal)
        if request.base_level != expected_level:
            raise RuntimeError(f"unexpected starting level: {request.base_level}")
        plan = rag.recommend(request)
        payload = plan.to_backend_payload()
        draft = call("POST", path + "/plans", 201, payload, token)
        day = payload["days"][0]["date"]
        if draft["plan"]["status"] != "draft" or store.get_card_for_child(child_id, day) is not None:
            raise RuntimeError("draft exposed active cards")
        plan_id = draft["plan"]["id"]
        call("POST", f"{path}/plans/{plan_id}/approve", 200, {}, token)
        current = store.get_card_for_child(child_id, day)
        upcoming = store.next_card_for_child(child_id, day)
        feedback = {"child_id": child_id, "date": day, "completion": "full", "satisfaction": 4,
                    "interest": 3, "comprehension": 4, "memo": "다른 자료로 바꿔 주세요."}
        result = coach.coach(coaching_request(child, feedback, today=current, next_card=upcoming,
                                              plan_status="approved", catalog=rag.catalog))
        if (result.case != "C" or not result.adjust["requires_parent_approval"]
                or not result.adjust["proposal"] or result.adjust["auto_apply"]):
            raise RuntimeError("change was not gated")
        if store.next_card_for_child(child_id, day) != upcoming:
            raise RuntimeError("AI adapter unexpectedly mutated the backend card")
        # Submitting a fresh draft via the existing upload route leaves the old approval active.
        call("POST", path + "/plans", 201, payload, token)
        if store.approved_plan(child_id)["id"] != plan_id:
            raise RuntimeError("new draft deactivated the approved plan")
        levels.append({"age": age, "level": request.base_level, "cards": len(draft["cards"]),
                       "coach_case": result.case, "change_requires_approval": True})
    return {"status": "passed", "profiles": levels}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backend_checkout", type=Path)
    args = parser.parse_args()
    backend = args.backend_checkout.resolve() / "backend"
    if not (backend / "main.py").is_file():
        parser.error("backend_checkout must contain backend/main.py")
    with TemporaryDirectory(prefix="bloomy-backend-smoke-") as directory:
        os.environ["BLOOMY_DB"] = str(Path(directory) / "smoke.sqlite3")
        os.environ.pop("DATABASE_URL", None)
        os.environ.pop("OPENAI_API_KEY", None)
        sys.path.insert(0, str(backend))
        print(json.dumps(verify(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
