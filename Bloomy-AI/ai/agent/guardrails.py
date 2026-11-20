"""Validate the action boundary independently of the message composer."""
from dataclasses import asdict
from .rules import decide

AI_LABEL = "AI가 작성한 코칭 메시지입니다."


def validate_result(result, request, tools):
    if result.case not in {"A", "B", "C", "SKIP"}:
        raise ValueError("invalid case")
    expected = decide(request.feedback, request.history, result.memo_intent)
    if result.case != expected["case"] or result.flags != expected["flags"] or result.low_interest_streak != expected["low_interest_streak"]:
        raise ValueError("message generation must not override rule decisions")
    if result.case == "SKIP":
        if result.message is not None or result.tomorrow is not None or result.adjust["type"] != "none":
            raise ValueError("rest days must not produce messages or adjustments")
        return result
    if not result.message or not result.message.endswith(AI_LABEL):
        raise ValueError("missing AI label")
    if result.confidence_sentence:
        raise ValueError("local v1 does not assert confidence without trend verification")
    adjustment = result.adjust
    if adjustment["type"] not in {"none", "shrink", "swap", "swap_easy", "propose_swap"}:
        raise ValueError("invalid adjustment type")
    active = request.plan_status == "approved"
    original = asdict(request.next_card) if request.next_card else None
    if not active and (result.tomorrow is not None or adjustment["type"] != "none"):
        raise ValueError("unapproved plans must not activate cards")
    if adjustment["requires_parent_approval"]:
        if adjustment["auto_apply"] or result.tomorrow != original or not active:
            raise ValueError("pending changes must not alter the effective next card")
    if adjustment["auto_apply"] and (not active or not original or adjustment["requires_parent_approval"]):
        raise ValueError("automatic adjustment requires an approved existing card")
    if adjustment["type"] == "none" and result.tomorrow != (original if active else None):
        raise ValueError("no-op must preserve the existing card")
    if result.flags["expert_referral"] and adjustment["type"] != "none":
        raise ValueError("referrals must not adjust learning plans")
    for card in (result.tomorrow, adjustment.get("proposal")):
        if card is None:
            continue
        item = tools.get_detail(card["content_id"])
        if not original or card["child_id"] != request.child_id or card["date"] != original["date"]:
            raise ValueError("invalid adjustment target")
        if type(card["minutes"]) is not int or not 5 <= card["minutes"] <= request.session_minutes:
            raise ValueError("invalid adjusted duration")
        if not item["age_min"] <= request.age <= item["age_max"]:
            raise ValueError("content age mismatch")
        if card["content_id"] != original["content_id"]:
            if card["task"] != item["task"] or card["check_point"] != item["check_point"]:
                raise ValueError("ungrounded adjustment")
    if adjustment["type"] == "shrink":
        expected = {**original, "minutes": max(5, original["minutes"] - 5)}
        if result.tomorrow != expected or not adjustment["auto_apply"]:
            raise ValueError("invalid shrink")
    if adjustment["type"] in {"swap", "swap_easy"}:
        old = tools.get_detail(original["content_id"])
        new = tools.get_detail(result.tomorrow["content_id"])
        expected_level = old["level"] if adjustment["type"] == "swap" else old["level"] - 1
        if (new["level"] != expected_level or new["type"] == old["type"] or new["skill"] != old["skill"] or
                new["id"] == old["id"] or result.tomorrow["minutes"] > original["minutes"]):
            raise ValueError("swap violates level, goal, format, or duration constraints")
    if adjustment["type"] == "propose_swap" and not adjustment["requires_parent_approval"]:
        raise ValueError("parent change requests require approval")
    if active and original and result.memo_intent == "change_request" and adjustment["type"] != "propose_swap":
        raise ValueError("parent changes must remain proposals")
    evidence_ids = {e["content_id"] for e in result.evidence}
    for evidence in result.evidence:
        if evidence != tools.evidence(tools.get_detail(evidence["content_id"])):
            raise ValueError("invalid evidence")
    for card in (result.tomorrow, adjustment.get("proposal")):
        if card and card["content_id"] not in evidence_ids:
            raise ValueError("missing card evidence")
    return result
