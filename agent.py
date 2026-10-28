"""Governed knowledge-to-action agent: Ask -> Ground -> Reason -> Act -> Approve -> Record.

The pipeline logic lives here; app.py only renders it. Design principle (slide 8):
the agent should know when to ACT, when to ASK, and when to STOP.
"""
import hashlib
import json
import random
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent
POLICY_FILE = HERE / "policies.json"
AUDIT_FILE = HERE / "audit_log.jsonl"

ACT, ASK, STOP = "ACT", "ASK", "STOP"

ACTIONS = ["AUTO_APPROVE", "MANAGER_APPROVAL_REQUIRED", "COMMITTEE_REVIEW_REQUIRED",
           "NEEDS_CLARIFICATION", "BLOCKED"]

CATEGORIES = [
    ("Travel & Events", ["travel", "conference", "offsite", "off-site", "flight", "hotel", "airfare"]),
    ("Software & Subscriptions", ["software", "subscription", "license", "licence", "saas", "renewal"]),
    ("IT Hardware", ["server", "hardware", "laptop", "computer", "monitor", "storage", "network", "printer"]),
    ("Professional Services", ["consultant", "contractor", "services", "training"]),
]

# JSON schema handed to Ollama's structured-output mode (works the same on watsonx.ai).
REASONING_SCHEMA = {
    "type": "object",
    "properties": {
        "request_summary": {"type": "string"},
        "recommended_action": {"type": "string", "enum": ACTIONS},
        "risk_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        "rationale": {"type": "string"},
        "clarifying_question": {"type": ["string", "null"]},
        "employee_response": {"type": "string"},
    },
    "required": ["request_summary", "recommended_action", "risk_level", "rationale",
                 "clarifying_question", "employee_response"],
}

SYSTEM_PROMPT = (
    "You are a procurement policy agent for a public-sector agency, built on IBM Granite. "
    "Answer ONLY from the retrieved policy excerpts; never invent policy. "
    "The REQUIRED ACTION has already been determined from governed policy data: set recommended_action to it. "
    "rationale: one sentence that cites the policy section number and explains why it applies. "
    "clarifying_question: a short question about the cost if the action is NEEDS_CLARIFICATION, otherwise null. "
    "employee_response: speak directly TO the employee in second person, following the reply guidance. "
    "Each text field under 30 words. Return JSON only."
)

REPLY_GUIDANCE = {
    "AUTO_APPROVE": "Tell them it is within the auto-approval limit and you have issued the order.",
    "MANAGER_APPROVAL_REQUIRED": "Tell them it needs their Department Manager's approval and you have drafted "
                                 "the requisition and routed it to the manager.",
    "COMMITTEE_REVIEW_REQUIRED": "Tell them it exceeds $5,000, so you have opened a Procurement Committee review "
                                 "case, and they will be notified of the decision.",
    "NEEDS_CLARIFICATION": "Ask them for the estimated total cost, because approval depends on the amount.",
    "BLOCKED": "Politely decline, name the policy concern, and say it has been referred to the Procurement "
               "Integrity Office for guidance.",
}


def load_policies():
    return json.loads(POLICY_FILE.read_text(encoding="utf-8"))


def new_run_id():
    return "run-" + uuid.uuid4().hex[:8]


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------- 2. Ground

_AMOUNT = re.compile(
    r"\$\s?(\d[\d,]*(?:\.\d+)?)\s?(k|m|thousand|million)?\b"
    r"|(\d[\d,]*(?:\.\d+)?)\s?(k|m|thousand|million)?\s?(?:dollars|usd)\b",
    re.I,
)
_SCALE = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}


def extract_amounts(text):
    amounts = []
    for m in _AMOUNT.finditer(text):
        number, scale = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        value = float(number.replace(",", ""))
        if scale:
            value *= _SCALE[scale.lower()]
        amounts.append(value)
    return amounts


def infer_category(text):
    lowered = text.lower()
    for name, words in CATEGORIES:
        if any(w in lowered for w in words):
            return name
    return "General Goods & Services"


def ground(query, policies):
    """Retrieve the approved policy sections that apply to this request."""
    t0 = time.perf_counter()
    amounts = extract_amounts(query)
    amount = max(amounts) if amounts else None

    tier_id = None
    if amount is not None:
        for tid, tier in policies["tiers"].items():
            if tier["min_amount"] <= amount <= tier["max_amount"]:
                tier_id = tid
                break
        if tier_id is None:  # gaps between tier bounds (e.g. $999.995) fall to the stricter tier
            tier_id = next(tid for tid, t in policies["tiers"].items() if amount <= t["max_amount"])

    lowered = query.lower()
    violations = [p for p in policies["prohibited_practices"] if any(k in lowered for k in p["keywords"])]

    excerpts = [t["policy"] for t in policies["tiers"].values()] + [p["policy"] for p in violations]
    return {
        "amounts_found": amounts,
        "amount": amount,
        "tier_id": tier_id,
        "tier": policies["tiers"].get(tier_id) if tier_id else None,
        "violations": violations,
        "category": infer_category(query),
        "excerpts": excerpts,
        "policy_document": policies["policy_document"],
        "retrieval_ms": round((time.perf_counter() - t0) * 1000, 2),
    }


# --------------------------------------------------------------------------- 3. Reason

def build_messages(query, grounding, guardrail):
    g = grounding
    lines = [f"Employee request: {query}", "", "Retrieved policy excerpts (authoritative):"]
    lines += [f"- {e}" for e in g["excerpts"]]
    lines.append("")
    lines.append(f"Detected amount: {'$' + format(g['amount'], ',.2f') if g['amount'] is not None else 'NONE'}")
    if g["tier"]:
        lines.append(f"Matched rule: Section {g['tier']['section']} -> {g['tier']['action']}")
    if g["violations"]:
        lines.append("Prohibited practice matched: " + "; ".join(f"Section {v['section']} ({v['title']})"
                                                            for v in g["violations"]))
    if guardrail["flagged"]:
        lines.append("Input guardrail: FLAGGED (" + ", ".join(c["risk"] for c in guardrail["checks"] if c["flagged"]) + ")")
    lines.append(f"Likely category: {g['category']}")
    required = expected_action(g, guardrail)
    lines.append(f"REQUIRED ACTION: {required}")
    lines.append(f"Reply guidance: {REPLY_GUIDANCE[required]}")
    return [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": "\n".join(lines)}]


def expected_action(grounding, guardrail):
    if grounding["violations"] or guardrail["flagged"]:
        return "BLOCKED"
    if grounding["amount"] is None:
        return "NEEDS_CLARIFICATION"
    return grounding["tier"]["action"]


def mock_reasoning(query, grounding, guardrail):
    """Deterministic stand-in for Granite when Ollama is unavailable."""
    g = grounding
    action = expected_action(g, guardrail)
    amt = f"${g['amount']:,.0f}" if g["amount"] is not None else None
    if action == "BLOCKED":
        v = g["violations"][0] if g["violations"] else None
        cite = f"Section {v['section']}" if v else "Input guardrail"
        return {
            "request_summary": f"Request involving {amt or 'an unspecified amount'} that conflicts with policy.",
            "recommended_action": action, "risk_level": "HIGH",
            "rationale": f"{cite}: " + (v["policy"].split(": ", 1)[1] if v else
                                        "the request attempts to bypass policy controls.")
                         + " No workflow may be opened.",
            "clarifying_question": None,
            "employee_response": "I can't help structure this request that way. I've referred it to the "
                                 "Procurement Integrity Office, who can advise on the right path.",
        }
    if action == "NEEDS_CLARIFICATION":
        return {
            "request_summary": "Purchase request without an estimated cost.",
            "recommended_action": action, "risk_level": "LOW",
            "rationale": "Sections 4.1-4.3 set approval authority by dollar amount, which was not provided.",
            "clarifying_question": "What is the estimated total cost of this purchase?",
            "employee_response": "Happy to help. What's the estimated total cost? "
                                 "That determines who needs to approve it.",
        }
    t = g["tier"]
    reply = {
        "AUTO_APPROVE": f"Good news: at {amt} this is within the auto-approval limit. I've issued the order.",
        "MANAGER_APPROVAL_REQUIRED": f"At {amt} this needs your Department Manager's approval. "
                                     "I've drafted the requisition and routed it to them.",
        "COMMITTEE_REVIEW_REQUIRED": f"At {amt} this exceeds $5,000, so the Procurement Committee must review it. "
                                     "I've opened the review case for you.",
    }[action]
    return {
        "request_summary": f"{g['category']} purchase request for {amt}.",
        "recommended_action": action, "risk_level": t["risk"],
        "rationale": f"{t['policy']} The requested amount of {amt} falls in this tier.",
        "clarifying_question": None, "employee_response": reply,
    }


def parse_reasoning(raw):
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start:end + 1])


def enforce(reasoning, grounding, guardrail):
    """Deterministic policy cross-check. Policy, not the model, has the final word."""
    required = expected_action(grounding, guardrail)
    model_says = reasoning.get("recommended_action")
    mode = STOP if required == "BLOCKED" else ASK if required == "NEEDS_CLARIFICATION" else ACT
    return {"mode": mode, "action": required, "model_action": model_says, "agreement": model_says == required}


# --------------------------------------------------------------------------- 4. Act

def draft_action(run_id, query, grounding, reasoning, decision):
    rng = random.Random(run_id)
    g = grounding
    category = g["category"]
    if decision["mode"] == ASK:
        return {"type": "clarification", "question": reasoning.get("clarifying_question")
                or "What is the estimated total cost of this purchase?"}
    if decision["mode"] == STOP:
        v = g["violations"][0] if g["violations"] else None
        return {"type": "blocked",
                "reason": v["policy"] if v else "Input guardrail flagged the request.",
                "referred_to": "Procurement Integrity Office (notification only, no workflow opened)"}

    t = g["tier"]
    prefix = "TA" if category.startswith("Travel") else "PO"
    doc_id = f"{prefix}-2026-{rng.randint(10000, 99999)}"
    skill = {
        "AUTO_APPROVE": "issue_purchase_order",
        "MANAGER_APPROVAL_REQUIRED": "create_requisition_and_route_to_manager",
        "COMMITTEE_REVIEW_REQUIRED": "open_procurement_committee_case",
    }[decision["action"]]
    return {
        "type": "workflow",
        "target_workflow": f"Procurement > {category} > {decision['action'].replace('_', ' ').title()}",
        "draft_id": doc_id,
        "amount": g["amount"],
        "category": category,
        "required_approver": t["approver"],
        "risk_level": reasoning.get("risk_level") or t["risk"],
        "sla": t["sla"],
        "policy_section": t["section"],
        "tool_call": {
            "tool": skill,
            "arguments": {
                "draft_id": doc_id, "amount_usd": g["amount"], "category": category,
                "justification": reasoning.get("request_summary", query)[:160],
                "policy_reference": f"{g['policy_document']['id']} §{t['section']}",
                "approver_role": t["approver"],
            },
        },
    }


# --------------------------------------------------------------------------- 6. Record

def _last_hash():
    if not AUDIT_FILE.exists():
        return "0" * 64
    lines = [l for l in AUDIT_FILE.read_text(encoding="utf-8").splitlines() if l.strip()]
    if not lines:
        return "0" * 64
    try:
        return json.loads(lines[-1]).get("record_hash", "0" * 64)
    except ValueError:
        return "0" * 64


def build_audit_record(run, cfg):
    R = run["R"]
    g, rsn, act, apv = R[2], R[3], R[4], R[5]
    d = rsn["decision"]
    status = {
        "APPROVED": "PASSED", "AUTO_APPROVED": "PASSED", "ESCALATED": "ESCALATED",
        "NOT_REQUIRED_ASK": "PENDING_CLARIFICATION", "NOT_REQUIRED_STOP": "BLOCKED",
    }[apv["decision"]]
    policy_id = g["policy_document"]["id"]
    if g["tier"]:
        grounding_id = f"{policy_id}/{g['tier_id']}/§{g['tier']['section']}"
    else:
        grounding_id = f"{policy_id}/none"
    if g["violations"]:
        grounding_id += " + " + ", ".join(f"§{v['section']}" for v in g["violations"])

    record = {
        "audit_id": f"AUD-{run['id'][4:].upper()}",
        "timestamp": now_iso(),
        "parent_run": run.get("parent"),
        "user_query": run["query"],
        "requester": R[1]["requester"],
        "policy_grounding_id": grounding_id,
        "policy_version": g["policy_document"]["version"],
        "model_id": cfg["watsonx_model_id"],
        "model_runtime": rsn["stats"]["runtime"] + ":" + rsn["stats"]["model"],
        "guardrail": {"method": rsn["guardrail"]["method"], "model": rsn["guardrail"]["model"],
                      "flagged": rsn["guardrail"]["flagged"]},
        "agent_recommendation": d["model_action"],
        "policy_enforced_action": d["action"],
        "model_policy_agreement": d["agreement"],
        "workflow": ({"tool": act["tool_call"]["tool"], "draft_id": act["draft_id"]}
                     if act["type"] == "workflow" else {"type": act["type"]}),
        "human_approver": apv["approver"],
        "approver_comment": apv.get("comment") or None,
        "decision": apv["decision"],
        "compliance_status": status,
        "metrics": {
            "cycle_time_s": round(time.time() - run["t0"], 1),
            "llm_latency_s": rsn["stats"]["latency_s"],
            "output_tokens": rsn["stats"]["output_tokens"],
        },
        "prev_hash": _last_hash(),
    }
    body = json.dumps(record, sort_keys=True, default=str).encode()
    record["record_hash"] = hashlib.sha256(body).hexdigest()
    return record


def append_audit(record):
    with AUDIT_FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


def read_audit():
    if not AUDIT_FILE.exists():
        return []
    out = []
    for line in AUDIT_FILE.read_text(encoding="utf-8").splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except ValueError:
                pass
    return out


def verify_chain(records):
    """Recompute every hash; True if the ledger has not been tampered with."""
    prev = "0" * 64
    for rec in records:
        body = {k: v for k, v in rec.items() if k != "record_hash"}
        digest = hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
        if rec.get("prev_hash") != prev or digest != rec.get("record_hash"):
            return False
        prev = rec["record_hash"]
    return True
