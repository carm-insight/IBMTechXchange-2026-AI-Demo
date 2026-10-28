# IBM watsonx | Governed Knowledge-to-Action Agent (Demo)

Live demo for **"Operationalizing AI in the Public Sector"** (IBM TechXchange 2026, Insight Public Sector).
It implements **Use case 1** from slide 8: **Ask → Ground → Reason → Act → Approve → Record**,
using open-source tools on a laptop, with every stage mapped to the IBM watsonx platform.

> *Design principle: the agent should know when to act, when to ask, and when to stop.*

| Stage | IBM platform (production) | This demo (open source, local) |
|---|---|---|
| 1. Ask | watsonx Orchestrate chat / channels | Streamlit text box |
| 2. Ground | watsonx.data (governed lakehouse + RAG) | `policies.json` + deterministic matcher |
| 3. Reason | watsonx.ai: IBM Granite + Granite Guardian | Granite + Granite Guardian in **Ollama** |
| 4. Act | watsonx Orchestrate agents & skills | Tool-call payload |
| 5. Approve | watsonx Orchestrate human-in-the-loop | Approval gate (execution truly halts) |
| 6. Record | watsonx.governance | Hash-chained `audit_log.jsonl` |

## Prerequisites

- **Python 3.10+** ([python.org](https://www.python.org/downloads/))
- **Ollama** ([ollama.com/download](https://ollama.com/download)) to run Granite locally. Optional: without it
  the app runs in offline mock mode.
- **RAM:** about 16 GB for the 3B model plus Guardian 8B. On smaller machines, skip the Guardian pull or use
  `granite4:micro`.

```bash
git clone <this repo URL>
cd <repo folder>
```

## Quick start (Windows)

Double-click **`run_demo.bat`**. It starts Ollama if needed and opens http://localhost:8501.

Manual (Windows, macOS, or Linux):
```powershell
pip install -r requirements.txt
ollama pull granite4.2:3b              # reasoning model (fast on a laptop)
ollama pull granite4.1-guardian:8b     # input guardrail (optional, recommended)
python -m streamlit run app.py
```
Any installed Granite model shows up in the sidebar picker (`granite4:micro`, `granite3.3:8b`, ...).
If Ollama or the models are missing, the app runs in **offline mock mode** automatically, so the demo still works.

## Before you go on stage

1. Launch the app 5 minutes early and click **🔥 Warm up Granite** in the sidebar. The first call otherwise pays a
   model-load cost.
2. Leave **Presenter mode** ON: one click per stage, so you control the pacing while you narrate.
3. Go to **Governance ledger → Clear ledger** so the audience sees a fresh evidence trail.
4. If the venue machine misbehaves, flip **Offline mock mode** on. The UI and flow are identical.
5. Browser zoom to 110-125% for the projector (Ctrl + / Ctrl -).
6. **Memory:** Granite 4.2 3B (~3.5 GB) + Guardian 4.1 8B (~7.7 GB) stay resident for 60 minutes. Close heavy apps
   first. If RAM is tight, switch the Guardian toggle off (the rule screen still catches scenario E) or pull
   `granite3-guardian:2b` (smaller, but it over-flagged normal requests in testing).
7. Ollama uses the Intel Arc GPU via Vulkan (`OLLAMA_VULKAN=1`, `OLLAMA_IGPU_ENABLE=1`, set by `run_demo.bat` and
   in your user environment). Run `ollama ps` and check for "100% GPU".

## Suggested run-of-show (after slide 8)

| Scenario | What it proves | Talk track |
|---|---|---|
| **A** - $4,500 server hardware | *Act, with a human in control* | "Grounded in §4.2. Granite drafts the requisition, then Orchestrate **halts**. Nothing executes until a manager clicks Approve." |
| **B** - $500 software renewal | *Know when to act* | "Below $1,000 the policy allows autonomous action. No human click, but it's still recorded." |
| **C** - $12,000 conference travel | *Escalate* | "Above $5,000: committee review. Try **Escalation required** to show the audit trail captures that too." |
| **D** - laptops, no amount | *Know when to ask* | "The agent won't guess. It asks a question. Type `About $2,400 for three laptops` and it resumes." |
| **E** - split a $9,000 order | *Know when to stop* | "Classic threshold-splitting. Policy §4.4 plus Granite Guardian stop it cold. No workflow is opened." |

Finish on the **Governance ledger** tab: requests, autonomous resolutions, human decisions, policy exceptions
stopped, model/policy disagreements, cycle time, and a verified hash chain. Those are the **Measures** on slide 8.
The **Architecture & IBM platform** tab is your slide-5 tie-back for Q&A.

## Agent trace panel (right side)

A live message bus showing every exchange in the run, with timings since the employee asked:
Employee → Procurement Agent → watsonx.data → Granite Guardian (criteria + `<score>` verdict) → IBM Granite
(grounded prompt, with the JSON response streaming in as it is generated) → Policy engine cross-check →
watsonx Orchestrate tool call → Approver → watsonx.governance (audit write + hash-chain ack).
Expand the ▸ rows to show the exact system prompt, the user message with injected policy, the JSON schema, and the
Guardian criteria. A clarifying-question follow-up (scenario D) continues in the same trace. Toggle it in the
sidebar (**Show agent trace panel**) if you want more room on a small screen.

Talk track: *"On the left is what the employee and approver see. On the right is what an auditor sees: every
model call, every guardrail verdict, every tool call, in order. That's the difference between a chatbot and a
governed agent."*

## How it works (for the technical audience)

- **Grounding first.** The amount and prohibited-practice keywords are matched against `policies.json`
  (versioned, owned) *before* the model runs. The retrieved excerpts are injected into the Granite prompt.
- **Guardrail.** Granite Guardian 4.1 screens the request with a **bring-your-own-criteria** rule written in
  plain English: prompt manipulation plus procurement circumvention (see `GUARDIAN_CHECKS` in `llm.py`).
  In testing it flagged only the split-purchase and prompt-injection requests, about 4 s per screen on the Arc GPU.
- **Structured reasoning.** Granite returns JSON constrained by a schema (Ollama structured outputs). Expand
  *Under the hood* on stage 3 to show the exact prompt and output.
- **Policy beats the model.** `agent.enforce()` recomputes the required action from policy. If Granite disagrees,
  policy wins and the disagreement is logged as an exception metric.
- **Tamper-evident evidence.** Each audit record carries `prev_hash` and `record_hash` (SHA-256). The ledger tab
  re-verifies the chain. Edit `audit_log.jsonl` by hand and it will show **BROKEN**.

## Moving to IBM watsonx in production

`llm.py` ends with a commented `ibm-watsonx-ai` block (`ModelInference.chat_stream`). The messages, schema,
grounding, and audit record are unchanged; only the runtime swaps. In production:
policies → **watsonx.data**, Granite + Guardian → **watsonx.ai**, tool call + approval → **watsonx Orchestrate**,
audit record → **watsonx.governance** (factsheets, evaluation, monitoring).

## Files

```
watsonx-agent-demo/
├── app.py             # Streamlit UI: stage indicator, explainers, approval gate, ledger
├── agent.py           # Pipeline: ground, prompt, policy enforcement, action drafting, audit hash chain
├── llm.py             # Ollama/Granite client, Granite Guardian, mock fallback, watsonx.ai parity block
├── policies.json      # Mock procurement policy (tiers §4.1-4.3, prohibited practices §4.4-4.5)
├── requirements.txt
├── run_demo.bat       # One-click launcher
└── .streamlit/config.toml
```

Thresholds, approvers, SLAs and prohibited practices live in `policies.json`, so you can change policy without
touching code. Changing it is also a good live moment: edit a threshold, rerun, and the audit record shows the new policy version.

## License

Apache License 2.0. See [LICENSE](LICENSE). IBM, watsonx, and Granite are trademarks of IBM. This is an
independent sample, not an official IBM product. The procurement policy and requesters are fictional.
