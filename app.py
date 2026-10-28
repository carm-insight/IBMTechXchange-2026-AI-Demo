"""IBM watsonx | Governed Knowledge-to-Action Agent: live demo for IBM TechXchange 2026.

Use case 1: Ask -> Ground -> Reason -> Act -> Approve -> Record
Run:  streamlit run app.py
"""
import html
import json
import time

import streamlit as st

import agent
import llm

st.set_page_config(page_title="watsonx Governed Agent Demo", page_icon="\U0001F6E1️",
                   layout="wide", initial_sidebar_state="expanded")

# --------------------------------------------------------------------------- content

SCENARIOS = [
    ("A", "Manager approval", "Can I auto-approve a purchase order for $4,500 for server hardware?",
     "Agent acts, then a human approves"),
    ("B", "Auto-approve", "Can I approve a $500 software subscription renewal?",
     "Agent acts on its own; policy allows it"),
    ("C", "Committee review", "Requesting $12,000 for offsite conference travel.",
     "Agent escalates to a committee"),
    ("D", "Missing info", "Can I buy new laptops for the onboarding team?",
     "Agent asks a clarifying question"),
    ("E", "Policy violation", "Can I split a $9,000 laptop order into two $4,500 POs so it only needs manager approval?",
     "Agent stops and refers it"),
]

STAGES = [
    dict(n=1, name="Ask", sub="“Which policy applies?”", ibm="End-user interface",
         what="An employee asks a plain-language question. There are no forms and no policy manual to search. "
              "The request is now a governed agent interaction with an identity and a timestamp.",
         platform="watsonx Orchestrate chat, or an existing portal / Teams / Slack channel.",
         demo="The text box in this app."),
    dict(n=2, name="Ground", sub="Retrieve approved sources", ibm="watsonx.data",
         what="Before the model generates a word, the agent retrieves the approved policy sources. The decision "
              "boundary comes from governed enterprise data, not from model memory, so it is current, owned, "
              "and citable.",
         platform="watsonx.data: governed lakehouse plus vector retrieval (RAG) over approved policy documents.",
         demo="policies.json with a deterministic amount and keyword matcher."),
    dict(n=3, name="Reason", sub="Apply role and context", ibm="watsonx.ai · IBM Granite",
         what="Granite Guardian screens the request first. IBM Granite then reasons over only the retrieved "
              "excerpts and returns structured JSON. Finally a deterministic cross-check makes sure the policy, "
              "not the model, has the last word.",
         platform="watsonx.ai hosting IBM Granite and Granite Guardian, with prompt templates and structured output.",
         demo="The same open-weight Granite model (Apache 2.0), running locally in Ollama on this laptop."),
    dict(n=4, name="Act", sub="Open the right workflow", ibm="watsonx Orchestrate",
         what="AI moves from answering to completing work. The agent picks the right workflow and drafts the "
              "transaction as a tool call. Or it decides not to act: it asks a question, or it stops.",
         platform="watsonx Orchestrate agents and tools/skills connected to ERP, case management and ticketing.",
         demo="A Python tool-call payload with the same shape an Orchestrate skill receives."),
    dict(n=5, name="Approve", sub="Keep humans in control", ibm="watsonx Orchestrate",
         what="The agent knows when to act, when to ask, and when to stop. Low-risk work runs on its own. "
              "Anything above the threshold halts here until an accountable human decides.",
         platform="watsonx Orchestrate human-in-the-loop approval steps and escalation routing.",
         demo="An approval gate. Execution truly pauses until you click."),
    dict(n=6, name="Record", sub="Preserve an audit trail", ibm="watsonx.governance",
         what="Every decision becomes evidence: the query, the policy version, the model, the guardrail result, "
              "the human approver and the outcome. Records are hash-chained, so tampering is detectable.",
         platform="watsonx.governance: AI inventory, factsheets, evaluation, monitoring and audit evidence.",
         demo="audit_log.jsonl, an append-only SHA-256 hash chain on disk."),
]

ACTION_LABEL = {
    "AUTO_APPROVE": "Auto-approve", "MANAGER_APPROVAL_REQUIRED": "Manager approval required",
    "COMMITTEE_REVIEW_REQUIRED": "Committee review required", "NEEDS_CLARIFICATION": "Needs clarification",
    "BLOCKED": "Blocked",
}
ACTION_TONE = {
    "AUTO_APPROVE": "green", "MANAGER_APPROVAL_REQUIRED": "yellow", "COMMITTEE_REVIEW_REQUIRED": "magenta",
    "NEEDS_CLARIFICATION": "blue", "BLOCKED": "red",
}
RISK_TONE = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red"}

# --------------------------------------------------------------------------- styling

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root{--navy:#001141;--navy2:#0b1f4d;--blue:#0f62fe;--blue-l:#edf5ff;--mag:#d02670;--green:#198038;
--green-l:#defbe6;--yellow:#8e6a00;--yellow-l:#fcf4d6;--red:#da1e28;--red-l:#fff1f1;--gray:#525252;
--line:#dde1e6;--bg:#f4f7fb;--card:#ffffff;--text:#161616;}
html,body,[class*="css"],.stMarkdown,.stButton button,input,textarea{font-family:'IBM Plex Sans',sans-serif !important;}
code,pre,.stJson{font-family:'IBM Plex Mono',monospace !important;}
.stApp{background:var(--bg);}
.block-container{padding-top:1.2rem;max-width:1500px;}
header[data-testid="stHeader"]{background:transparent;}
.stDeployButton,[data-testid="stAppDeployButton"]{display:none;}
.hero{background:linear-gradient(100deg,var(--navy) 0%,#0a2a6b 60%,#0f62fe 140%);color:#fff;border-radius:6px;
padding:22px 28px 18px;margin-bottom:14px;position:relative;overflow:hidden;}
.hero:before{content:"";position:absolute;top:0;left:0;right:0;height:5px;background:var(--mag);}
.hero .eyebrow{font-size:.78rem;letter-spacing:.18em;font-weight:600;color:#a6c8ff;text-transform:uppercase;}
.hero h1{color:#fff;font-size:2.0rem;font-weight:700;margin:4px 0 2px;padding:0;line-height:1.2;}
.hero .tag{font-size:1.02rem;color:#d0e2ff;}
.hero .pill{display:inline-block;background:var(--blue);color:#fff;font-size:.8rem;font-weight:600;padding:4px 12px;
border-radius:4px;margin-top:10px;margin-right:8px;}
.hero .partners{position:absolute;right:28px;bottom:16px;font-size:.78rem;font-weight:700;letter-spacing:.12em;color:#c6c6c6;}
.steps{display:flex;align-items:stretch;gap:6px;margin:4px 0 16px;}
.step{flex:1;background:var(--card);border:1.5px solid var(--line);border-radius:6px;padding:10px 10px 9px;
text-align:center;min-width:0;transition:all .3s;}
.step .nm{font-weight:700;font-size:1.12rem;color:var(--navy);}
.step .sb{font-size:.78rem;color:var(--gray);margin-top:2px;}
.step .pr{font-size:.68rem;font-weight:600;color:var(--blue);margin-top:6px;letter-spacing:.02em;}
.step .st{font-size:.66rem;font-weight:700;letter-spacing:.1em;margin-top:5px;color:#a8a8a8;}
.step.active{border-color:var(--blue);background:var(--blue-l);box-shadow:0 0 0 3px rgba(15,98,254,.18);}
.step.active .nm{color:var(--blue);} .step.active .st{color:var(--blue);}
.step.done{border-color:#a7f0ba;} .step.done .st{color:var(--green);}
.step.stopped{border-color:var(--mag);background:#fff0f7;} .step.stopped .st{color:var(--mag);}
.step.skipped{opacity:.55;}
.chev{display:flex;align-items:center;color:var(--mag);font-size:1.5rem;font-weight:700;}
.sec-h{display:flex;align-items:baseline;gap:12px;margin:0 0 8px;}
.sec-h .num{background:var(--navy);color:#fff;border-radius:50%;width:30px;height:30px;display:inline-flex;
align-items:center;justify-content:center;font-weight:700;font-size:.95rem;flex:none;}
.sec-h .ttl{font-size:1.35rem;font-weight:700;color:var(--navy);}
.sec-h .sub{font-size:.95rem;color:var(--gray);}
.explain{background:#f2f4f8;border-left:4px solid var(--blue);border-radius:4px;padding:12px 14px;font-size:.88rem;}
.explain .lbl{font-size:.68rem;font-weight:700;letter-spacing:.14em;color:var(--gray);margin-top:8px;}
.explain .lbl:first-child{margin-top:0;}
.explain .ibm{display:inline-block;background:var(--navy);color:#fff;font-weight:600;font-size:.78rem;
padding:2px 8px;border-radius:3px;margin:3px 0 2px;}
.explain p{margin:2px 0 0;}
.badge{display:inline-block;padding:3px 10px;border-radius:12px;font-size:.8rem;font-weight:700;letter-spacing:.03em;}
.b-green{background:var(--green-l);color:var(--green);} .b-yellow{background:var(--yellow-l);color:var(--yellow);}
.b-red{background:var(--red-l);color:var(--red);} .b-blue{background:var(--blue-l);color:var(--blue);}
.b-magenta{background:#ffd6e8;color:#9f1853;} .b-gray{background:#e0e0e0;color:#393939;}
.query{font-size:1.25rem;font-weight:500;color:var(--navy);background:#fff;border:1px solid var(--line);
border-left:5px solid var(--mag);padding:14px 18px;border-radius:4px;}
.meta{font-size:.8rem;color:var(--gray);margin-top:6px;}
table.pol{width:100%;border-collapse:collapse;font-size:.9rem;background:#fff;}
table.pol th{background:#e8ecf2;text-align:left;padding:7px 10px;font-weight:600;color:var(--navy);}
table.pol td{padding:7px 10px;border-top:1px solid var(--line);}
table.pol tr.hit td{background:var(--blue-l);font-weight:600;}
table.pol tr.viol td{background:var(--red-l);font-weight:600;color:#a2191f;}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:6px 0 10px;}
.kv div{background:#fff;border:1px solid var(--line);border-radius:4px;padding:9px 12px;}
.kv .k{font-size:.68rem;letter-spacing:.1em;font-weight:700;color:var(--gray);text-transform:uppercase;}
.kv .v{font-size:1.02rem;font-weight:600;color:var(--navy);margin-top:2px;word-break:break-word;}
.reply{background:#fff;border:1px solid var(--line);border-radius:14px 14px 14px 2px;padding:12px 16px;
font-size:1.02rem;color:var(--text);margin:8px 0;}
.reply .who{font-size:.72rem;font-weight:700;color:var(--blue);letter-spacing:.08em;margin-bottom:3px;}
.gate{border:2px dashed var(--yellow);background:var(--yellow-l);border-radius:6px;padding:14px 18px;margin-bottom:10px;}
.gate h4{margin:0 0 4px;color:#684e00;}
.runtime{font-size:.8rem;color:var(--gray);margin:4px 0 8px;}
.side-brand{font-size:1.25rem;font-weight:700;color:var(--navy);} .side-brand span{color:var(--blue);}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:6px;}
.mapping td,.mapping th{font-size:.92rem;}
.stButton button p{white-space:normal;line-height:1.25;}
[data-stale="true"],.stale-element{opacity:1 !important;transition:none !important;}
[data-testid="stColumn"]:has(.st-key-trace_wrap){position:sticky;top:3.2rem;align-self:flex-start;}
.tv-head{position:relative;z-index:5;margin-bottom:0;background:var(--navy);color:#fff;border-radius:6px 6px 0 0;padding:10px 14px 9px;border-top:4px solid var(--mag);
font-weight:700;letter-spacing:.14em;font-size:.78rem;}
.tv-head span{display:block;font-weight:400;letter-spacing:0;color:#a6c8ff;font-size:.78rem;margin-top:2px;}
.tv-head .live{display:inline-block;width:8px;height:8px;border-radius:50%;background:#42be65;margin-right:7px;
box-shadow:0 0 0 3px rgba(66,190,101,.25);}
.st-key-agent_trace{background:#0b1530;border-radius:0 0 6px 6px;padding:2px 12px 8px;height:calc(100vh - 12.5rem) !important;
min-height:420px;}
.st-key-agent_trace [data-testid="stMarkdownContainer"] p{color:#a8a8a8;}
.tv-ev{border-left:3px solid #33415f;padding:5px 0 7px 10px;margin:4px 0;color:#dde1e6;font-size:.8rem;}
.tv-h{display:flex;flex-wrap:wrap;align-items:center;gap:5px;}
.tv-t{font-family:'IBM Plex Mono',monospace;color:#8d8d8d;font-size:.68rem;min-width:46px;}
.tv-chip{border:1px solid var(--c);color:var(--c);border-radius:10px;padding:0 7px;font-size:.7rem;font-weight:600;
white-space:nowrap;}
.tv-arr{color:#6f6f6f;font-size:.8rem;}
.tv-kind{margin-left:auto;font-size:.6rem;letter-spacing:.12em;color:#a8a8a8;font-weight:700;}
.tv-title{color:#fff;font-weight:600;margin-top:4px;line-height:1.3;}
.tv-good .tv-title{color:#6fdc8c;} .tv-bad .tv-title{color:#ff8389;} .tv-bad{border-left-color:#fa4d56 !important;}
.tv-body{color:#c6c6c6;margin-top:2px;line-height:1.35;}
.tv-code{display:block;background:#050b1c;color:#a6c8ff;font-family:'IBM Plex Mono',monospace;font-size:.69rem;line-height:1.4;
padding:6px 8px;border-radius:4px;margin:5px 0 0;white-space:pre-wrap;word-break:break-word;max-height:230px;overflow:auto;}
.tv-ev details{margin-top:4px;} .tv-ev summary{cursor:pointer;color:#78a9ff;font-size:.72rem;}
.tv-meta{color:#8d8d8d;font-size:.66rem;margin-top:3px;font-family:'IBM Plex Mono',monospace;}
.tv-empty{color:#8d8d8d;font-size:.85rem;padding:18px 4px;line-height:1.5;}
.tv-empty b{color:#dde1e6;}
[data-testid="stSkillsNudge"],[data-testid="stSkillsNudgeAnchor"],[data-testid="stSkillsInstallCallout"]{display:none !important;}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


def h(text):
    # Escape HTML, and "$" so Streamlit markdown never renders "$1,000 - $5,000" as LaTeX math.
    return html.escape(str(text)).replace("$", "&#36;")


def badge(text, tone="gray"):
    return f'<span class="badge b-{tone}">{h(text)}</span>'


def money(v):
    return f"${v:,.2f}".replace(".00", "") if v is not None else "n/a"


# --------------------------------------------------------------------------- agent trace

ACTORS = {
    "employee": ("Employee", "#ee5396"),
    "agent": ("Procurement Agent", "#4589ff"),
    "data": ("watsonx.data", "#08bdba"),
    "guardian": ("Granite Guardian", "#a56eff"),
    "granite": ("IBM Granite", "#33b1ff"),
    "policy": ("Policy engine", "#a8a8a8"),
    "orchestrate": ("watsonx Orchestrate", "#78a9ff"),
    "human": ("Approver", "#f1c21b"),
    "gov": ("watsonx.governance", "#42be65"),
    "integrity": ("Integrity Office", "#fa4d56"),
}
TRACE = None  # the trace panel's container during this script run (None when the panel is hidden)


def _pre(text):
    # One physical line, so Streamlit's markdown parser keeps the whole event as a single HTML block.
    return '<div class="tv-code">' + h(text).replace("\n", "<br>") + "</div>"


def event_html(ev, streaming=False):
    src, dst = ACTORS[ev["src"]], ACTORS[ev["dst"]]
    tone = f' tv-{ev["tone"]}' if ev.get("tone") else ""
    parts = [f'<div class="tv-ev{tone}" style="border-left-color:{src[1]}"><div class="tv-h">'
             f'<span class="tv-t">+{ev["t"]:05.1f}s</span>'
             f'<span class="tv-chip" style="--c:{src[1]}">{h(src[0])}</span><span class="tv-arr">→</span>'
             f'<span class="tv-chip" style="--c:{dst[1]}">{h(dst[0])}</span>'
             f'<span class="tv-kind">{h(ev["kind"])}</span></div>']
    if ev.get("title"):
        parts.append(f'<div class="tv-title">{h(ev["title"])}</div>')
    if ev.get("body"):
        parts.append(f'<div class="tv-body">{h(ev["body"])}</div>')
    if ev.get("code") is not None:
        parts.append(_pre(ev["code"] + ("▌" if streaming else "")))
    for label, text in ev.get("details") or []:
        parts.append(f"<details><summary>{h(label)}</summary>{_pre(text)}</details>")
    if ev.get("meta"):
        parts.append(f'<div class="tv-meta">{h(ev["meta"])}</div>')
    return "".join(parts) + "</div>"


def emit(run, src, dst, kind, title="", body=None, code=None, details=None, meta=None, tone=None, live=True):
    """Append one message to the run's trace and, during a live script run, draw it in the panel."""
    ev = {"t": time.time() - run["t0"], "src": src, "dst": dst, "kind": kind, "title": title, "body": body,
          "code": code, "details": details, "meta": meta, "tone": tone}
    run["trace"].append(ev)
    if live and TRACE is not None:
        TRACE.markdown(event_html(ev), unsafe_allow_html=True)
    return ev


# --------------------------------------------------------------------------- state

ss = st.session_state
ss.setdefault("run", None)
ss.setdefault("query_input", SCENARIOS[0][2])
ss.setdefault("policies", agent.load_policies())


def set_query(text):
    ss.query_input = text


def start_run(cfg, parent=None):
    q = ss.query_input.strip()
    if not q:
        return
    prev = ss.run if (parent and ss.run) else None  # a clarification reply continues the same conversation
    ss.run = {"id": agent.new_run_id(), "query": q, "t0": prev["t0"] if prev else time.time(), "R": {},
              "cfg": dict(cfg), "parent": parent, "target": 1 if cfg["presenter"] else 6,
              "trace": list(prev["trace"]) if prev else []}


def next_stage():
    ss.run["target"] += 1


def reset():
    ss.run = None


def decide(decision, approver, comment_key):
    run = ss.run
    comment = ss.get(comment_key, "")
    run["R"][5] = {"decision": decision, "approver": approver, "comment": comment, "at": agent.now_iso()}
    run["target"] = 6
    a = run["R"][4]
    # Runs as a widget callback (before the rerun), so record without drawing; the rerun replays it.
    emit(run, "human", "orchestrate", "DECISION", decision.title(), body=approver,
         meta=f'comment: "{comment}"' if comment else None,
         tone="good" if decision == "APPROVED" else None, live=False)
    if decision == "APPROVED":
        emit(run, "orchestrate", "agent", "EXECUTED", f'{a["tool_call"]["tool"]} resumed and executed',
             meta=f'{a["draft_id"]} · {money(a["amount"])}', tone="good", live=False)
    else:
        emit(run, "orchestrate", "agent", "ROUTED", "Workflow escalated for further review, not executed",
             meta=a["draft_id"], live=False)


def continue_with_reply(run_id, key):
    reply = ss.get(key, "").strip()
    if not reply:
        return
    ss.query_input = f"{ss.run['query']} {reply}"
    start_run(ss.run["cfg"], parent=run_id)


# --------------------------------------------------------------------------- sidebar

with st.sidebar:
    st.markdown('<div class="side-brand">IBM <span>watsonx</span></div>'
                '<div style="font-size:.8rem;color:#525252;margin-bottom:8px">Governed agent demo · '
                'open-source local stack</div>', unsafe_allow_html=True)

    st.markdown("**Runtime**")
    up = llm.server_up()
    models = llm.list_models() if up else []
    granite = llm.granite_models(models)
    guardians = llm.guardian_models(models)
    if up:
        st.markdown(f'<span class="dot" style="background:#24a148"></span>Ollama {h(llm.server_version())} '
                    f'running', unsafe_allow_html=True)
    else:
        st.markdown('<span class="dot" style="background:#da1e28"></span>Ollama not reachable',
                    unsafe_allow_html=True)
        if llm.find_ollama_exe() and st.button("Start Ollama", width="stretch"):
            with st.spinner("Starting Ollama..."):
                llm.start_server()
            st.rerun()

    model = st.selectbox("Reasoning model (IBM Granite)", granite or ["(none installed)"],
                         help="Granite models found in Ollama. Pull more with: ollama pull granite4:micro")
    if not granite:
        model = None
        if up:
            st.caption("No Granite model found. Run `ollama pull granite4:micro`.")
    use_guardian = st.toggle("Granite Guardian input guardrail",
                             value=bool(guardians) and not guardians[0].startswith("granite3"),
                             disabled=not guardians,
                             help="Screens requests with a plain-English custom rule: prompt manipulation or "
                                  "procurement circumvention (Guardian 4.x bring-your-own-criteria). Without it, "
                                  "a transparent rule screen is used.")
    if guardians and use_guardian:
        st.caption(f"Guardrail model: `{guardians[0]}`")
    guardian = guardians[0] if (guardians and use_guardian) else None
    force_mock = st.toggle("Offline mock mode", value=not (up and granite),
                           help="Deterministic fallback with no model calls. Use it if the venue laptop has problems.")
    live = bool(up and model and not force_mock)
    if live and st.button("\U0001F525 Warm up Granite", width="stretch",
                          help="Loads the model into memory so the first live call is fast."):
        with st.spinner(f"Loading {model}..."):
            try:
                secs = llm.warm_up(model)
                if guardian:
                    llm.warm_up(guardian)
                st.success(f"Ready ({secs:.1f}s)")
            except Exception as exc:  # noqa: BLE001 - surface any runtime issue to the presenter
                st.error(f"Warm-up failed: {exc}")
    st.caption(f"Mode: **{'LIVE: ' + model if live else 'MOCK (offline fallback)'}**")

    st.divider()
    st.markdown("**Presentation**")
    presenter = st.toggle("Presenter mode (one stage per click)", value=True,
                          help="Off = the agent runs straight through and stops only at the human approval gate.")
    explain = st.toggle("Show \u201cWhat you're seeing\u201d panels", value=True)
    show_trace = st.toggle("Show agent trace panel", value=True,
                           help="Live message bus: every exchange between the agent, IBM Granite, "
                                "Granite Guardian, Orchestrate, the approver and watsonx.governance.")
    pacing = st.slider("Auto-mode pacing (seconds per stage)", 0.0, 3.0, 1.0, 0.25, disabled=presenter)
    approver_name = st.text_input("Approver name (Approve stage)", "Dana Whitfield, Dept. Manager")
    st.divider()
    st.button("↺ Reset demo", on_click=reset, width="stretch")

cfg = {"live": live, "model": model, "guardian": guardian if live else None, "presenter": presenter,
       "pacing": pacing, "approver": approver_name,
       "watsonx_model_id": llm.watsonx_equivalent(model if live else "granite4")}

# --------------------------------------------------------------------------- header

st.markdown(
    '<div class="hero"><div class="eyebrow">IBM TechXchange 2026 · Use case 1 · Tangible pattern</div>'
    '<h1>A governed knowledge-to-action agent</h1>'
    '<div class="tag">From trusted enterprise data to governed agents, automated action, and measurable '
    'mission outcomes</div>'
    '<span class="pill">watsonx.ai + watsonx.data</span><span class="pill">watsonx Orchestrate</span>'
    '<span class="pill">watsonx.governance</span>'
    '<div class="partners">INSIGHT &nbsp;|&nbsp; IBM &nbsp;|&nbsp; TD SYNNEX / TECH DATA</div></div>',
    unsafe_allow_html=True)


def stage_status(n):
    run = ss.run
    if run is None:
        return ("active", "READY") if n == 1 else ("pending", "")
    R = run["R"]
    mode = R[3]["decision"]["mode"] if 3 in R else None
    if n in R:
        if n == 4 and mode == agent.ASK:
            return "stopped", "ASKED"
        if n == 4 and mode == agent.STOP:
            return "stopped", "STOPPED"
        if n == 5 and mode in (agent.ASK, agent.STOP):
            return "skipped", "NOT NEEDED"
        if n == 5:
            return "done", {"APPROVED": "APPROVED", "AUTO_APPROVED": "AUTONOMOUS",
                            "ESCALATED": "ESCALATED"}.get(R[5]["decision"], "DONE")
        return "done", "✓ DONE"
    first_missing = next((s["n"] for s in STAGES if s["n"] not in R), None)
    if n == first_missing:
        if n == 5 and n <= run["target"]:
            return "active", "WAITING FOR HUMAN"
        return "active", "IN PROGRESS" if n <= run["target"] else "NEXT"
    return "pending", ""


def steps_html():
    parts = []
    for s in STAGES:
        cls, label = stage_status(s["n"])
        parts.append(f'<div class="step {cls}"><div class="nm">{s["n"]}. {s["name"]}</div>'
                     f'<div class="sb">{h(s["sub"])}</div><div class="pr">{h(s["ibm"])}</div>'
                     f'<div class="st">{label or "&nbsp;"}</div></div>')
    return '<div class="steps">' + '<div class="chev">❯</div>'.join(parts) + '</div>'


tab_live, tab_arch, tab_ledger = st.tabs(["▶  Live agent", "\U0001F3DB  Architecture & IBM platform",
                                          "\U0001F4DC  Governance ledger"])

# --------------------------------------------------------------------------- stage renderers

def section(s, show_explain):
    box = st.container(border=True)
    if show_explain:
        left, right = box.columns([2.6, 1], gap="large")
        right.markdown(
            f'<div class="explain"><div class="lbl">WHAT YOU\'RE SEEING</div><p>{h(s["what"])}</p>'
            f'<div class="lbl">IBM PLATFORM</div><div class="ibm">{h(s["ibm"])}</div><p>{h(s["platform"])}</p>'
            f'<div class="lbl">IN THIS DEMO (OPEN SOURCE)</div><p>{h(s["demo"])}</p></div>',
            unsafe_allow_html=True)
    else:
        left = box
    left.markdown(f'<div class="sec-h"><span class="num">{s["n"]}</span><span class="ttl">{s["name"]}</span>'
                  f'<span class="sub">{h(s["sub"])}</span></div>', unsafe_allow_html=True)
    return left


def compute_ask(run, body):
    r = {"query": run["query"], "requester": "j.morales@agency.gov (Facilities Operations)",
         "channel": "Employee portal \u2192 watsonx Orchestrate", "received": agent.now_iso()}
    if run.get("parent"):
        emit(run, "employee", "agent", "REPLY", "Employee answered the clarifying question",
             body=run["query"], meta=f'continues {run["parent"]}')
    else:
        emit(run, "employee", "agent", "MESSAGE", body=run["query"],
             meta=f'{r["requester"]} \u00b7 session {run["id"]}')
    return r


def render_ask(r, body):
    body.markdown(f'<div class="query">“{h(r["query"])}”</div>'
                  f'<div class="meta">\U0001F464 {h(r["requester"])} &nbsp;·&nbsp; \U0001F4E5 {h(r["channel"])}'
                  f' &nbsp;·&nbsp; \U0001F552 {h(r["received"])}</div>', unsafe_allow_html=True)


def compute_ground(run, body):
    g = agent.ground(run["query"], ss.policies)
    doc = g["policy_document"]
    emit(run, "agent", "data", "QUERY", "Retrieve approved policy sources",
         code=(f'collection: {doc["id"]} (v{doc["version"]}, owner: {doc["owner"]})\n'
               f'amount_detected: {money(g["amount"]) if g["amount"] is not None else "none"}\n'
               f'screen: approval tiers + prohibited practices'))
    if g["violations"]:
        title = "Prohibited practice matched: " + ", ".join(f'\u00a7{v["section"]} {v["title"]}' for v in g["violations"])
        tone = "bad"
    elif g["tier"]:
        title, tone = f'Matched \u00a7{g["tier"]["section"]} \u2192 {ACTION_LABEL[g["tier"]["action"]]}', None
    else:
        title, tone = "No amount in request: approval tier cannot be determined", None
    emit(run, "data", "agent", "RESULT", title, tone=tone,
         details=[(f'{len(g["excerpts"])} approved excerpts returned', "\n".join(g["excerpts"]))],
         meta=f'{g["retrieval_ms"]} ms \u00b7 category: {g["category"]}')
    return g


def render_ground(g, body):
    doc = g["policy_document"]
    tier = g["tier"]
    cells = [("Amount detected", money(g["amount"]) if g["amount"] is not None else "None found"),
             ("Matched rule", f"Section {tier['section']}" if tier else "n/a"),
             ("Policy action", ACTION_LABEL[tier["action"]] if tier else "Cannot determine"),
             ("Retrieval", f"{g['retrieval_ms']} ms")]
    body.markdown('<div class="kv">' + "".join(f'<div><div class="k">{h(k)}</div><div class="v">{h(v)}</div></div>'
                                               for k, v in cells) + '</div>', unsafe_allow_html=True)
    rows = []
    for tid, t in ss.policies["tiers"].items():
        cls = "hit" if tid == g["tier_id"] else ""
        mark = "▶ MATCH" if cls else ""
        rows.append(f'<tr class="{cls}"><td>§{t["section"]}</td><td>{h(t["policy"].split(": ", 1)[1])}</td>'
                    f'<td>{badge(ACTION_LABEL[t["action"]], ACTION_TONE[t["action"]])}</td><td>{mark}</td></tr>')
    for p in ss.policies["prohibited_practices"]:
        hit = p in g["violations"]
        rows.append(f'<tr class="{"viol" if hit else ""}"><td>§{p["section"]}</td>'
                    f'<td>{h(p["policy"].split(": ", 1)[1])}</td><td>{badge("Prohibited", "red")}</td>'
                    f'<td>{"⛔ MATCH" if hit else ""}</td></tr>')
    body.markdown(f'<div class="meta" style="margin-bottom:4px">Source: <b>{h(doc["title"])}</b> · {h(doc["id"])} '
                  f'v{h(doc["version"])} · owner: {h(doc["owner"])}</div>'
                  '<table class="pol"><tr><th>Section</th><th>Approved policy text</th><th>Outcome</th><th></th></tr>'
                  + "".join(rows) + '</table>', unsafe_allow_html=True)
    if g["violations"]:
        body.error(f"⛔ Prohibited practice detected: Section {g['violations'][0]['section']} "
                   f"({g['violations'][0]['title']}). This must not become a transaction.")
    elif g["amount"] is None:
        body.warning("No dollar amount in the request. Approval authority depends on amount, "
                     "so the policy can't be applied yet.")
    else:
        body.success(f"Grounded: {money(g['amount'])} → Section {tier['section']} → "
                     f"{ACTION_LABEL[tier['action']]}.")


def compute_reason(run, body):
    c = run["cfg"]
    g = run["R"][2]
    plan = llm.guardian_plan(c["guardian"])
    if c["guardian"]:
        emit(run, "agent", "guardian", "REQUEST", "Screen the request before any reasoning",
             code=f'model: {c["guardian"]}\ncriteria: {", ".join(n for n, _ in plan)}\nuser: {run["query"]}',
             details=[(f"Criteria \u201c{n}\u201d ({'built-in risk' if ' ' not in cr else 'plain-English, bring your own'})",
                       cr) for n, cr in plan],
             meta="POST /api/chat \u00b7 think=false \u00b7 temperature 0")
    else:
        emit(run, "agent", "guardian", "REQUEST", "Screen the request (rule-based backstop)",
             body="Granite Guardian is off or not installed; transparent regex rules stand in.")
    with body.status("\U0001F6E1\uFE0F Granite Guardian screening the request..." if c["guardian"]
                     else "\U0001F6E1\uFE0F Screening the request...", expanded=False) as s:
        guard = llm.guardian_screen(run["query"], c["guardian"])
        s.update(label="Input guardrail complete", state="error" if guard["flagged"] else "complete")
    flagged = [ck["risk"] for ck in guard["checks"] if ck["flagged"]]
    emit(run, "guardian", "agent", "VERDICT",
         ("FLAGGED: " + ", ".join(flagged)) if flagged else "Clear: no risk detected",
         code="\n".join(f'{ck["risk"]}: {ck["raw"]}' for ck in guard["checks"]),
         meta=f'{guard["latency_ms"]} ms \u00b7 {guard["method"]}' + (f' \u00b7 {guard["note"]}' if guard.get("note") else ""),
         tone="bad" if flagged else "good")
    messages = agent.build_messages(run["query"], g, guard)
    required = agent.expected_action(g, guard)
    emit(run, "agent", "granite", "REQUEST", "Grounded prompt + JSON schema",
         body=f"Retrieved policy injected as context. Required action from policy: {required}.",
         details=[("System prompt", messages[0]["content"]),
                  ("User message (retrieved policy injected)", messages[1]["content"]),
                  ("Output JSON schema", json.dumps(agent.REASONING_SCHEMA, indent=1, ensure_ascii=False))],
         meta=(f'POST /api/chat \u00b7 {c["model"]} \u00b7 format=json-schema \u00b7 temperature 0'
               if c["live"] else "offline mock runtime (no model call)"))
    stream_ev = emit(run, "granite", "agent", "STREAMING", "Structured response", code="", live=False)
    trace_ph = TRACE.empty() if TRACE is not None else None
    last_draw = 0.0
    note = None
    body.markdown(f'<div class="runtime">\U0001F9E0 IBM Granite is reasoning over the retrieved policy '
                  f'({h(c["model"] + " via Ollama, local" if c["live"] else "mock fallback")})...</div>',
                  unsafe_allow_html=True)
    live_box = body.empty()
    raw, stats = "", None

    def run_stream(stream):
        nonlocal raw, stats
        nonlocal last_draw
        for kind, val in stream:
            if kind == "token":
                raw += val
                live_box.code(raw, language="json")
                if trace_ph is not None and time.time() - last_draw > 0.12:
                    trace_ph.markdown(event_html({**stream_ev, "code": raw}, streaming=True),
                                      unsafe_allow_html=True)
                    last_draw = time.time()
            else:
                stats = val

    if c["live"]:
        try:
            run_stream(llm.chat_stream(c["model"], messages, schema=agent.REASONING_SCHEMA))
            reasoning = agent.parse_reasoning(raw)
        except Exception as exc:  # noqa: BLE001 - never let the stage demo crash
            note = f"Live Granite call failed ({exc.__class__.__name__}: {str(exc)[:120]}). Used offline fallback."
            raw = ""
            reasoning = None
    else:
        reasoning = None
    if reasoning is None:
        if note:
            emit(run, "agent", "agent", "FALLBACK", "Live Granite call failed: using offline fallback",
                 body=note, tone="bad")
        mock = agent.mock_reasoning(run["query"], g, guard)
        run_stream(llm.mock_stream(json.dumps(mock, indent=2)))
        reasoning = mock
    live_box.empty()
    stream_ev.update(kind="RESPONSE", code=json.dumps(reasoning, indent=1, ensure_ascii=False),
                     meta=(f'{stats["output_tokens"]} tokens \u00b7 {stats["tokens_per_sec"]} tok/s \u00b7 '
                           f'{stats["latency_s"]} s \u00b7 {stats["model"]}' if stats["runtime"] == "ollama"
                           else "mock Granite (deterministic)"))
    if trace_ph is not None:
        trace_ph.markdown(event_html(stream_ev), unsafe_allow_html=True)
    decision = agent.enforce(reasoning, g, guard)
    emit(run, "policy", "agent", "CROSS-CHECK",
         ("Model agrees with policy" if decision["agreement"] else "Override: policy wins over the model")
         + f' \u2192 {decision["mode"]}',
         code=f'model:  {decision["model_action"]}\npolicy: {decision["action"]}',
         tone="good" if decision["agreement"] else "bad")
    return {"guardrail": guard, "messages": messages, "raw": raw, "reasoning": reasoning, "stats": stats,
            "note": note, "decision": decision}


def render_reason(r, body):
    gd, rs, d, stx = r["guardrail"], r["reasoning"], r["decision"], r["stats"]
    checks = " · ".join(f'{c["risk"]}{" (custom criteria)" if c.get("custom") else ""}: '
                             f'<b>{"FLAGGED" if c["flagged"] else "clear"}</b>' for c in gd["checks"])
    who = f"Granite Guardian ({gd['model']})" if gd["method"] == "granite-guardian" else "Rule-based screen"
    tone = "red" if gd["flagged"] else "green"
    body.markdown(f'{badge("GUARDRAIL", tone)} &nbsp;{h(who)}: {checks} &nbsp;'
                  f'<span class="meta">({gd["latency_ms"]} ms)</span>', unsafe_allow_html=True)
    if r["note"]:
        body.warning(r["note"])
    if stx["runtime"] == "ollama":
        rt = (f'IBM Granite · <b>{h(stx["model"])}</b> via Ollama (local) · {stx["output_tokens"]} tokens '
              f'· {stx["tokens_per_sec"]} tok/s · {stx["latency_s"]} s')
    else:
        rt = "Mock Granite (offline fallback) · deterministic response"
    body.markdown(f'<div class="runtime">\U0001F9E0 {rt}</div>', unsafe_allow_html=True)

    a = rs.get("recommended_action", "?")
    cells = [("Request", rs.get("request_summary", "")), ("Category", ss.run["R"][2]["category"]),
             ("Recommendation", ACTION_LABEL.get(a, a)), ("Risk", rs.get("risk_level", ""))]
    body.markdown('<div class="kv">' + "".join(f'<div><div class="k">{h(k)}</div><div class="v">{h(v)}</div></div>'
                                               for k, v in cells) + '</div>', unsafe_allow_html=True)
    body.markdown(f'**Rationale:** {h(rs.get("rationale", ""))}', unsafe_allow_html=True)
    body.markdown(f'<div class="reply"><div class="who">AGENT → EMPLOYEE</div>{h(rs.get("employee_response", ""))}'
                  f'</div>', unsafe_allow_html=True)
    if d["agreement"]:
        body.success(f"✔ Deterministic policy cross-check: the model's recommendation matches the "
                     f"policy-required action ({ACTION_LABEL[d['action']]}).")
    else:
        body.warning(f"⚠ Policy cross-check: the model said {ACTION_LABEL.get(d['model_action'], d['model_action'])}, "
                     f"but policy requires {ACTION_LABEL[d['action']]}. Policy wins, and the disagreement is logged "
                     f"as a model exception.")
    with body.expander("Under the hood: prompt sent to Granite, and raw JSON returned"):
        st.markdown("**System prompt**")
        st.code(r["messages"][0]["content"], language="text", wrap_lines=True)
        st.markdown("**Grounded user message** (the retrieved context is injected here)")
        st.code(r["messages"][1]["content"], language="text", wrap_lines=True)
        st.markdown("**Structured output** (JSON schema enforced)")
        st.json(rs)
        st.markdown("**Guardrail criteria** (Granite Guardian; a custom rule is plain English, with no retraining)")
        for name, crit in llm.GUARDIAN_CHECKS:
            st.markdown(f"- `{name}`: " + ("built-in risk definition" if crit == name else crit))


def compute_act(run, body):
    R = run["R"]
    a = agent.draft_action(run["id"], run["query"], R[2], R[3]["reasoning"], R[3]["decision"])
    reply = R[3]["reasoning"].get("employee_response", "")
    if a["type"] == "workflow":
        emit(run, "agent", "orchestrate", "TOOL CALL", a["tool_call"]["tool"],
             code=json.dumps(a["tool_call"]["arguments"], indent=1, ensure_ascii=False), meta="drafted \u00b7 not yet executed")
        emit(run, "agent", "employee", "MESSAGE", body=reply)
    elif a["type"] == "clarification":
        emit(run, "agent", "employee", "QUESTION", body=a["question"],
             meta="no workflow opened \u00b7 waiting for the employee")
    else:
        emit(run, "agent", "integrity", "REFERRAL", "No workflow opened: request referred",
             body=a["reason"], tone="bad")
        emit(run, "agent", "employee", "MESSAGE", body=reply)
    return a


def render_act(a, body):
    run = ss.run
    if a["type"] == "clarification":
        body.info("✋ **The agent knows when to ask.** It won't guess an amount and route a transaction "
                  "on an assumption. No workflow was opened.")
        body.markdown(f'<div class="reply"><div class="who">AGENT → EMPLOYEE</div>{h(a["question"])}</div>',
                      unsafe_allow_html=True)
        key = f"reply_{run['id']}"
        c1, c2 = body.columns([3, 1])
        c1.text_input("Employee reply", key=key, placeholder="e.g. About $2,400 for three laptops",
                      label_visibility="collapsed")
        c2.button("Send reply →", key=f"send_{run['id']}", on_click=continue_with_reply,
                  args=(run["id"], key), type="primary", width="stretch")
        return
    if a["type"] == "blocked":
        body.error("\U0001F6D1 **The agent knows when to stop.** No purchase order or workflow was opened.")
        body.markdown(f"**Reason:** {h(a['reason'])}  \n**Referred to:** {h(a['referred_to'])}",
                      unsafe_allow_html=True)
        return
    cells = [("Target workflow", a["target_workflow"]), ("Draft ID", a["draft_id"]),
             ("Required approver", a["required_approver"]), ("Risk level", a["risk_level"]),
             ("Amount", money(a["amount"])), ("Category", a["category"]),
             ("Policy", f"Section {a['policy_section']}"), ("SLA", a["sla"])]
    body.markdown('<div class="kv">' + "".join(f'<div><div class="k">{h(k)}</div><div class="v">{h(v)}</div></div>'
                                               for k, v in cells) + '</div>', unsafe_allow_html=True)
    body.markdown("**watsonx Orchestrate tool call** (drafted, not yet executed):")
    body.json(a["tool_call"])


def compute_approve(run, body):
    """Return a decision if no human is needed; None means halt at the gate."""
    d = run["R"][3]["decision"]
    if d["mode"] == agent.ASK:
        return {"decision": "NOT_REQUIRED_ASK", "approver": "N/A (no action drafted)", "at": agent.now_iso()}
    if d["mode"] == agent.STOP:
        return {"decision": "NOT_REQUIRED_STOP", "approver": "N/A (action blocked)", "at": agent.now_iso()}
    a = run["R"][4]
    if d["action"] == "AUTO_APPROVE":
        sec = run["R"][2]["tier"]["section"]
        emit(run, "policy", "orchestrate", "AUTHORIZE", f"Autonomous execution permitted (\u00a7{sec})",
             body="Below the $1,000 threshold, so no human approval is required.")
        emit(run, "orchestrate", "agent", "EXECUTED", f'{a["tool_call"]["tool"]} executed',
             meta=f'{a["draft_id"]} \u00b7 {money(a["amount"])}', tone="good")
        return {"decision": "AUTO_APPROVED", "approver": f"Policy \u00a7{sec} (autonomous execution)",
                "at": agent.now_iso()}
    if not run.get("gate_sent"):  # the gate re-renders on every rerun while waiting; announce it once
        run["gate_sent"] = True
        emit(run, "orchestrate", "human", "APPROVAL REQUEST", f'{a["tool_call"]["tool"]} \u00b7 {money(a["amount"])}',
             body=f'Requires {a["required_approver"]} under \u00a7{a["policy_section"]}.',
             meta="execution paused until a human decides")
    return None


def render_gate(run, body):
    a = run["R"][4]
    body.markdown(f'<div class="gate"><h4>⏸ Human oversight gate: execution halted</h4>'
                  f'<b>{h(a["tool_call"]["tool"])}</b> for <b>{money(a["amount"])}</b> requires '
                  f'<b>{h(a["required_approver"])}</b> under Section {h(a["policy_section"])}. The agent cannot '
                  f'continue until an accountable human decides.</div>', unsafe_allow_html=True)
    ck = f"comment_{run['id']}"
    body.text_input("Approver comment (optional, goes into the audit record)", key=ck,
                    placeholder="e.g. Budget confirmed against FY26 capital plan")
    who = run["cfg"]["approver"] if a["policy_section"] == "4.2" else f"{run['cfg']['approver']} (for Procurement Committee)"
    c1, c2, _ = body.columns([1, 1, 2])
    c1.button("✅ Approve action", type="primary", width="stretch", key=f"ok_{run['id']}",
              on_click=decide, args=("APPROVED", who, ck))
    c2.button("❌ Escalation required", width="stretch", key=f"esc_{run['id']}",
              on_click=decide, args=("ESCALATED", who, ck))


def render_approve(p, body):
    msg = {
        "AUTO_APPROVED": ("success", "⚡ **The agent knows when to act.** Policy permits autonomous execution "
                          "below $1,000, so no human click was needed. The order was issued and the decision is still "
                          f"recorded. Approver of record: {p['approver']}."),
        "APPROVED": ("success", f"✅ Approved by **{p['approver']}** at {p['at']}. watsonx Orchestrate resumes "
                     "the workflow."),
        "ESCALATED": ("warning", f"⤴ Escalated by **{p['approver']}** at {p['at']}. The workflow is routed "
                      "for further review instead of executing."),
        "NOT_REQUIRED_ASK": ("info", "Nothing to approve. The agent paused to ask for information instead of acting."),
        "NOT_REQUIRED_STOP": ("info", "Nothing to approve. The agent refused to open a workflow."),
    }[p["decision"]]
    getattr(body, msg[0])(msg[1])
    if p.get("comment"):
        body.caption(f"Approver comment: {p['comment']}")


def compute_record(run, body):
    rec = agent.build_audit_record(run, run["cfg"])
    agent.append_audit(rec)
    keys = ["audit_id", "policy_grounding_id", "model_id", "agent_recommendation", "policy_enforced_action",
            "human_approver", "decision", "compliance_status"]
    emit(run, "agent", "gov", "WRITE", f'Audit record {rec["audit_id"]}',
         code="\n".join(f"{k}: {rec[k]}" for k in keys))
    emit(run, "gov", "agent", "ACK", f'Evidence chained \u00b7 {rec["compliance_status"]}',
         meta=f'sha256 {rec["record_hash"][:16]}\u2026 \u2190 prev {rec["prev_hash"][:12]}\u2026',
         tone="bad" if rec["compliance_status"] == "BLOCKED" else "good")
    return rec


def render_record(rec, body):
    tone = {"PASSED": "green", "ESCALATED": "yellow", "BLOCKED": "red", "PENDING_CLARIFICATION": "blue"}
    body.markdown(f'{badge("watsonx.governance audit log", "blue")} &nbsp; compliance_status: '
                  f'{badge(rec["compliance_status"], tone[rec["compliance_status"]])} &nbsp; '
                  f'<span class="meta">record_hash {rec["record_hash"][:16]}… chained to '
                  f'{rec["prev_hash"][:12]}…</span>', unsafe_allow_html=True)
    m1, m2, m3, m4 = body.columns(4)
    m1.metric("Cycle time", f"{rec['metrics']['cycle_time_s']} s")
    m2.metric("Model latency", f"{rec['metrics']['llm_latency_s']} s")
    m3.metric("Agrees with policy", "Yes" if rec["model_policy_agreement"] else "Exception")
    m4.metric("Human decided", "Yes" if rec["decision"] in ("APPROVED", "ESCALATED") else "No")
    body.json(rec)
    body.download_button("⬇ Download audit record (JSON)", json.dumps(rec, indent=2),
                         file_name=f"{rec['audit_id']}.json", mime="application/json")


COMPUTE = {1: compute_ask, 2: compute_ground, 3: compute_reason, 4: compute_act, 5: compute_approve, 6: compute_record}
RENDER = {1: render_ask, 2: render_ground, 3: render_reason, 4: render_act, 5: render_approve, 6: render_record}
SPINNER = {2: "Retrieving approved policy sources from the governed store...",
           4: "Drafting the workflow action...", 6: "Writing evidence to the governance log..."}

# --------------------------------------------------------------------------- live tab

with tab_live:
    steps_ph = st.empty()
    steps_ph.markdown(steps_html(), unsafe_allow_html=True)

    if show_trace:
        main_col, trace_col = st.columns([2.35, 1], gap="medium")
        with trace_col, st.container(key="trace_wrap", gap=None):
            st.markdown('<div class="tv-head"><i class="live"></i>AGENT TRACE'
                        '<span>Live message bus: agent \u00b7 IBM Granite \u00b7 Granite Guardian \u00b7 '
                        'Orchestrate \u00b7 governance</span></div>', unsafe_allow_html=True)
            TRACE = st.container(height=720, key="agent_trace", autoscroll=True, gap="xxsmall")
            if ss.run:
                for ev in ss.run["trace"]:
                    TRACE.markdown(event_html(ev), unsafe_allow_html=True)
            else:
                TRACE.markdown('<div class="tv-empty"><b>Run a scenario to watch the agents talk.</b><br>Every '
                               'message between the agent, the governed policy store, Granite Guardian, IBM '
                               'Granite, watsonx Orchestrate, the human approver and watsonx.governance '
                               'appears here, live, with timings.</div>', unsafe_allow_html=True)
    else:
        main_col = st.container()

    with main_col:
        with st.container(border=True):
            if explain:
                qcol, ecol = st.columns([2.6, 1], gap="large")
            else:
                qcol, ecol = st.container(), None
            with qcol:
                st.markdown('<div class="sec-h"><span class="num">•</span><span class="ttl">Employee question</span>'
                            '<span class="sub">Pick a scenario or type your own</span></div>', unsafe_allow_html=True)
                cols = st.columns(len(SCENARIOS))
                for col, (sid, label, text, hint) in zip(cols, SCENARIOS):
                    col.button(f"{sid} · {label}", key=f"sc_{sid}", on_click=set_query, args=(text,),
                               width="stretch", help=f"{hint}\n\n“{text}”")
                st.text_area("Employee request", key="query_input", height=80, label_visibility="collapsed")
                b1, b2 = st.columns([1, 3])
                b1.button("▶ Run agent", type="primary", on_click=start_run, args=(cfg,),
                          width="stretch")
                b2.caption("Presenter mode: one stage per click." if presenter else
                           "Auto mode: runs straight through and halts only where a human is required.")
            if ecol:
                ecol.markdown('<div class="explain"><div class="lbl">DESIGN PRINCIPLE</div>'
                              '<p><b>The agent should know when to act, when to ask, and when to stop.</b></p>'
                              '<div class="lbl">SCENARIOS</div><p>A · act + human approval<br>B · act autonomously'
                              '<br>C · escalate to committee<br>D · ask for missing info<br>E · stop: '
                              'policy violation</p></div>', unsafe_allow_html=True)

        run = ss.run
        if run:
            R = run["R"]
            for s in STAGES:
                n = s["n"]
                if n not in R and n > run["target"]:
                    st.button(f"▶  Next: {n}. {s['name']} ({s['sub']})", type="primary", on_click=next_stage,
                              key=f"next_{run['id']}_{n}")
                    break
                body = section(s, explain)
                if n not in R:
                    steps_ph.markdown(steps_html(), unsafe_allow_html=True)
                    if not run["cfg"]["presenter"] and n > 1 and run["cfg"]["pacing"]:
                        with body:
                            with st.spinner(SPINNER.get(n, "Working...")):
                                time.sleep(run["cfg"]["pacing"])
                    result = COMPUTE[n](run, body)
                    if result is None:  # human gate: halt
                        render_gate(run, body)
                        break
                    R[n] = result
                RENDER[n](R[n], body)
            steps_ph.markdown(steps_html(), unsafe_allow_html=True)
            if 6 in R:
                st.markdown('<div style="text-align:center;color:#d02670;font-weight:700;font-size:1.05rem;'
                            'margin:10px 0 4px">Start narrow. Design for trust. Measure the outcome. Scale the pattern.'
                            '</div>', unsafe_allow_html=True)

# --------------------------------------------------------------------------- architecture tab

with tab_arch:
    st.markdown("### Open source on the laptop, IBM watsonx in production")
    st.markdown("The same pattern and the same Granite model family. What changes is the operating layer you need "
                "to run it at scale: security, integration, automation, hybrid infrastructure, and human oversight.")
    rows = [
        ("1. Ask", "User inquiry", "watsonx Orchestrate chat / channels", "Streamlit text box"),
        ("2. Ground", "Policy RAG retrieval", "watsonx.data (lakehouse + vector retrieval)", "policies.json + matcher"),
        ("3. Reason", "Contextual LLM processing", "watsonx.ai: IBM Granite + Granite Guardian",
         "Granite + Granite Guardian in Ollama"),
        ("4. Act", "Workflow orchestration", "watsonx Orchestrate agents & skills", "Python tool-call payload"),
        ("5. Approve", "Human-in-the-loop", "watsonx Orchestrate approvals", "Streamlit approval gate"),
        ("6. Record", "Governance & audit", "watsonx.governance", "Hash-chained audit_log.jsonl"),
    ]
    st.markdown('<table class="pol mapping"><tr><th>Stage</th><th>Architecture</th><th>IBM platform (production)</th>'
                '<th>This demo (open source, local)</th></tr>'
                + "".join(f"<tr><td><b>{a}</b></td><td>{b}</td><td><b style='color:#0f62fe'>{c}</b></td><td>{d}</td></tr>"
                          for a, b, c, d in rows) + "</table>", unsafe_allow_html=True)
    st.write("")
    c1, c2, c3 = st.columns(3)
    with c1, st.container(border=True):
        st.markdown("**Why IBM Granite**")
        st.markdown("- Open weights under Apache 2.0: run it on a laptop, on-prem, or air-gapped\n"
                    "- Enterprise-focused family: instruct, Guardian (guardrails), embedding, vision\n"
                    "- Hosted and governed on watsonx.ai, with IBM's IP indemnity for its models\n"
                    "- Small models like `granite4:micro` make agents cheap enough to run everywhere")
    with c2, st.container(border=True):
        st.markdown("**Governance built in, not bolted on**")
        st.markdown("- **Inventory**: model, policy version and agent recorded on every action\n"
                    "- **Policy**: deterministic rules override model output\n"
                    "- **Evaluation**: model/policy agreement tracked as a metric\n"
                    "- **Oversight**: explicit human gates above thresholds\n"
                    "- **Evidence**: tamper-evident, hash-chained audit trail")
    with c3, st.container(border=True):
        st.markdown("**Public-sector applications**")
        st.markdown("Procurement · grants · HR · constituent service · policy compliance\n\n"
                    "**Measures**: cycle time · resolution rate · rework · adoption · "
                    "policy exceptions")
    st.markdown("#### Production parity: one function swap")
    st.code('''from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference

model = ModelInference(
    model_id="ibm/granite-3-3-8b-instruct",
    credentials=Credentials(url=WATSONX_URL, api_key=WATSONX_APIKEY),
    project_id=WATSONX_PROJECT_ID,
    params={"temperature": 0, "max_tokens": 450},
)
for chunk in model.chat_stream(messages=messages):   # same messages and schema as the local demo
    ...''', language="python")

# --------------------------------------------------------------------------- ledger tab

with tab_ledger:
    records = agent.read_audit()
    st.markdown("### watsonx.governance evidence ledger")
    if not records:
        st.info("No records yet. Run a scenario in the Live agent tab.")
    else:
        intact = agent.verify_chain(records)
        (st.success if intact else st.error)(
            f"Hash chain {'verified: all ' + str(len(records)) + ' records intact' if intact else 'BROKEN: ledger was modified'}.")
        n = len(records)
        status = [r["compliance_status"] for r in records]
        auto = sum(r["decision"] == "AUTO_APPROVED" for r in records)
        human = sum(r["decision"] in ("APPROVED", "ESCALATED") for r in records)
        exc = sum(r["compliance_status"] == "BLOCKED" for r in records)
        disagree = sum(not r.get("model_policy_agreement", True) for r in records)
        avg = sum(r["metrics"]["cycle_time_s"] for r in records) / n
        k = st.columns(6)
        k[0].metric("Requests", n)
        k[1].metric("Resolved autonomously", auto)
        k[2].metric("Human decisions", human)
        k[3].metric("Policy exceptions stopped", exc)
        k[4].metric("Model/policy disagreements", disagree)
        k[5].metric("Avg cycle time", f"{avg:.1f} s")
        table = [{"time": r["timestamp"][11:19], "audit_id": r["audit_id"], "query": r["user_query"][:70],
                  "grounding": r["policy_grounding_id"], "decision": r["decision"],
                  "status": r["compliance_status"], "approver": r["human_approver"],
                  "model": r["model_runtime"], "hash": r["record_hash"][:12]} for r in reversed(records)]
        st.dataframe(table, width="stretch", hide_index=True)
        c1, c2 = st.columns([1, 4])
        c1.download_button("⬇ Export ledger (JSONL)", agent.AUDIT_FILE.read_text(encoding="utf-8"),
                           file_name="watsonx_governance_audit_log.jsonl")
        if c2.button("Clear ledger (start fresh for a new audience)"):
            agent.AUDIT_FILE.unlink(missing_ok=True)
            st.rerun()
