"""Lightweight local GUI for Josie 1.0."""

from __future__ import annotations

import json
import tkinter as tk
import re
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from .config import Config
from .diagnostics import (
    external_storage_snapshot, health_check, memory_export_snapshot, recovery_snapshot,
    repository_snapshot, restore_drill_snapshot, storage_snapshot, system_snapshot, uptime_snapshot,
)
from .providers import provider_status
from .storage import LocalStore
from .reports import export_diagnostics, warning_snapshot
from .roadmap import roadmap_summary
from .tools import available_tools
from .policy import permission_for
from .provenance import INTERVIEW_QUESTIONS, origin_workflow_status
from .jobs import JobRunner, available_job_handlers
from .local_model import propose_local_actions


def respond(message: str, *, config: Config, project_root: Path, store: LocalStore | None = None) -> str:
    """Handle a deliberately small, local-only conversational command set."""
    text = message.strip().lower()
    if not text:
        return "Please type a request."
    if text in {"help", "?", "commands"} or "what can you do" in text:
        return (
            "I can check health, show cloud status, list allowed tools, report the time, remember notes, "
            "manage tasks, ask the local planning model, and draft manual Sophie/Bernie handoffs. "
            "Try: 'ask Josie ...', 'ask Sophie ...', 'ask Bernie ...', 'remember ...', "
            "'memories', 'add task ...', 'tasks', or 'complete task 1'. Model proposals are review-only; "
            "cloud calls are locked off."
        )
    if text in {"status", "dashboard", "summary", "josie status"}:
        health = health_check(config=config, project_root=project_root)
        counts = store.counts() if store else {"memories": 0, "pending_tasks": 0, "messages": 0}
        cloud = "ON" if config.allow_cloud else "LOCKED OFF"
        return (
            f"Status: {health['status']}. Disk free: {health['disk_free_gb']} GB. "
            f"Pending tasks: {counts['pending_tasks']}. Memories: {counts['memories']}. "
            f"Approvals waiting: {counts['pending_approvals']}. Conversation entries: {counts['messages']}. "
            f"Cloud: {cloud}."
        )
    if text in {"ledger", "upgrade fund", "fund status", "upgrade fund ledger"}:
        summary = store.ledger_summary() if store else {
            "actual_revenue_cents": 0, "actual_cost_cents": 0, "actual_balance_cents": 0,
            "estimated_revenue_cents": 0, "estimated_cost_cents": 0,
            "estimated_savings_cents": 0,
        }
        return (
            f"Upgrade Fund actual: revenue ${summary['actual_revenue_cents']/100:.2f}, "
            f"costs ${summary['actual_cost_cents']/100:.2f}, balance ${summary['actual_balance_cents']/100:.2f}. "
            f"Estimates (not earned money): revenue ${summary['estimated_revenue_cents']/100:.2f}, "
            f"costs ${summary['estimated_cost_cents']/100:.2f}, savings ${summary['estimated_savings_cents']/100:.2f}. "
            "This ledger cannot spend or move money."
        )
    if text in {"jobs", "job status", "orchestration jobs"}:
        summary = store.job_summary() if store else {}
        return "Jobs: " + ", ".join(f"{key} {value}" for key, value in summary.items()) + "."
    if text.startswith("queue job "):
        if store is None:
            return "The local job queue is unavailable."
        handler = text.removeprefix("queue job ").strip().replace("-", "_").replace(" ", "_")
        if handler not in available_job_handlers():
            return "Allowed job handlers: " + ", ".join(available_job_handlers()) + "."
        job_id = JobRunner(config=config, project_root=project_root, store=store).queue(handler)
        return f"Local allowlisted job {job_id} queued for {handler}."
    if text in {"run one job", "run next job"}:
        if store is None:
            return "The local job queue is unavailable."
        result = JobRunner(config=config, project_root=project_root, store=store).run_one()
        return f"Job runner: {result['status']}." if result["status"] == "idle" else f"Job {result['job_id']}: {result['status']}."
    if text.startswith("ask josie ") or text.startswith("ask local "):
        prefix = "ask josie " if text.startswith("ask josie ") else "ask local "
        request_text = message.strip()[len(prefix):].strip()
        try:
            result = propose_local_actions(request_text, config=config, project_root=project_root)
        except (RuntimeError, ValueError) as exc:
            return f"The local planning model could not produce a safe proposal: {exc}. Nothing was executed."
        proposal_id = None
        if store:
            proposal_id = store.record_model_proposal(
                user_input=request_text,
                model=str(result["model"]),
                response_json=json.dumps(result, sort_keys=True),
            )
        lines = [str(result["reply"])]
        actions = result["proposals"]
        if actions:
            lines.append("Review-only proposals:")
            lines.extend(
                f"- {item['handler']}: {item['reason']}" for item in actions
            )
        if proposal_id is not None:
            lines.append(f"Proposal record {proposal_id} was saved locally.")
        lines.append("No action was queued or executed.")
        return "\n".join(lines)
    if text.startswith("ask sophie ") or text.startswith("ask bernie "):
        if store is None:
            return "The local handoff inbox is unavailable."
        target = "sophie" if text.startswith("ask sophie ") else "bernie"
        prefix = f"ask {target} "
        request_text = message.strip()[len(prefix):].strip()
        try:
            handoff = store.create_model_handoff(target=target, request=request_text)
        except ValueError as exc:
            return f"{exc}. No handoff was created."
        mode = "ChatGPT/Codex Remote" if target == "sophie" else "Gemini free-tier chat"
        return (
            f"Handoff {handoff['id']} to {target.title()} is saved locally as a draft for manual "
            f"relay through {mode}. API budget is $0.00. Nothing was sent and no cloud API was called."
        )
    if text in {"handoffs", "model handoffs", "sophie handoffs", "bernie handoffs"}:
        items = store.recent_model_handoffs() if store else []
        if not items:
            return "No Sophie or Bernie handoff drafts are recorded."
        return "Model handoffs:\n" + "\n".join(
            f"{item['id']}. [{item['status']}] {item['target'].title()}: {item['request']}"
            for item in items
        )
    handoff_answer = re.fullmatch(
        r"record handoff answer (\d+)\s*:\s*(.+)", message.strip(), re.IGNORECASE
    )
    if handoff_answer:
        if store is None:
            return "The local handoff inbox is unavailable."
        handoff_id = int(handoff_answer.group(1))
        try:
            changed = store.record_model_handoff_answer(
                handoff_id=handoff_id, response=handoff_answer.group(2)
            )
        except ValueError as exc:
            return f"{exc}. No answer was recorded."
        return (
            f"Handoff {handoff_id} answer was recorded locally as untrusted text. Nothing was executed."
            if changed else f"Draft handoff {handoff_id} was not found."
        )
    if text in {"model proposals", "local proposals", "proposal history"}:
        items = store.recent_model_proposals() if store else []
        if not items:
            return "No local-model proposals are recorded."
        return "Local-model proposals:\n" + "\n".join(
            f"{item['id']}. [{item['status']}] {item['model']} | {item['created_at']}"
            for item in items
        )
    if text in {"external proposals", "webui proposals", "proposal inbox"}:
        items = store.recent_external_proposals() if store else []
        if not items:
            return "No external proposals are awaiting review."
        return "External review proposals:\n" + "\n".join(
            f"{item['id']}. [{item['status']}] {item['kind']}: {item['summary']}"
            for item in items
        )
    if text in {"origin interview", "origin questions", "provenance interview"}:
        status = origin_workflow_status(project_root)
        return (
            "Origin interview is local and ready; no model has been contacted.\n" +
            "\n".join(f"{index}. {question}" for index, question in enumerate(INTERVIEW_QUESTIONS, 1)) +
            f"\nWorkflow: {status['document']}"
        )
    if text.startswith("record origin from "):
        if store is None:
            return "The provenance record is unavailable."
        payload = message.strip()[19:].strip()
        source, separator, statement = payload.partition(":")
        if not separator:
            return "Use: record origin from SOURCE: STATEMENT"
        try:
            record_id = store.record_provenance(source=source, statement=statement)
        except ValueError as exc:
            return str(exc) + ". Nothing was recorded."
        return f"Origin record {record_id} saved as unverified from {source.strip()}."
    if text in {"origin records", "provenance", "project history"}:
        records = store.provenance_records() if store else []
        return "No origin records yet." if not records else "Origin records:\n" + "\n".join(
            f"{record_id}. [{status}] {source}: {statement}"
            for record_id, source, statement, status in records
        )
    origin_decision = re.fullmatch(r"(confirm|reject) origin (\d+)", text)
    if origin_decision:
        if store is None:
            return "The provenance record is unavailable."
        verb, raw_id = origin_decision.groups()
        decision = "confirmed" if verb == "confirm" else "rejected"
        changed = store.decide_provenance(int(raw_id), decision)
        return (
            f"Origin record {raw_id} marked {decision}."
            if changed else f"Unverified origin record {raw_id} was not found."
        )
    if text.startswith("permission ") or text.startswith("may you "):
        prefix = "permission " if text.startswith("permission ") else "may you "
        capability = text.removeprefix(prefix).strip()
        result = permission_for(capability, project_root)
        labels = {
            "autonomous": "allowed autonomously",
            "approval_required": "requires immediate human approval",
            "forbidden": "forbidden",
        }
        known = "known capability" if result["known"] == "true" else "unknown capability; fail-closed default"
        return f"{result['capability']}: {labels[result['decision']]} ({known})."
    ledger_match = re.fullmatch(
        r"record (actual|estimated) (revenue|expense|api cost|electricity|savings) "
        r"\$?(\d+(?:\.\d{1,2})?) for (.+)", text
    )
    if ledger_match:
        if store is None:
            return "The local ledger is unavailable."
        basis, category, amount, description = ledger_match.groups()
        category = category.replace(" ", "_")
        try:
            entry_id = store.record_ledger_entry(
                basis=basis, category=category, amount=amount, description=description
            )
        except ValueError as exc:
            return str(exc) + ". No ledger entry was created."
        return (
            f"Ledger entry {entry_id} recorded locally as {basis} {category.replace('_', ' ')} "
            f"${float(amount):.2f}. This recorded a fact only; no transaction occurred."
        )
    if text.startswith("request action "):
        if store is None:
            return "Approval inbox is unavailable."
        description = message.strip()[15:].strip()
        approval_id = store.request_approval(description)
        return f"Approval request {approval_id} recorded: {description}. Nothing has been executed."
    if text in {"approvals", "approval inbox", "pending approvals"}:
        items = store.pending_approvals() if store else []
        return "No pending approvals." if not items else "Pending approvals:\n" + "\n".join(f"{i}. {value}" for i, value in items)
    if text.startswith("approve ") or text.startswith("deny "):
        if store is None:
            return "Approval inbox is unavailable."
        decision_word, _, raw_id = text.partition(" ")
        if not raw_id.isdigit():
            return f"Please use a request number, such as '{decision_word} 1'."
        decision = "approved" if decision_word == "approve" else "denied"
        changed = store.decide_approval(int(raw_id), decision)
        if not changed:
            return f"Pending approval {raw_id} was not found."
        return f"Approval {raw_id} marked {decision}. No action was executed."
    if text in {"activity", "audit", "audit history", "recent activity"}:
        items = store.recent_activity() if store else []
        return "No audited activity yet." if not items else "Recent activity:\n" + "\n".join(f"{when} | {event} | {detail}" for when, event, detail in items)
    reminder_match = re.fullmatch(r"remind me in (\d+) minutes? to (.+)", text)
    if reminder_match:
        if store is None:
            return "Local reminders are unavailable."
        minutes = int(reminder_match.group(1))
        if minutes < 1 or minutes > 10080:
            return "Reminder time must be between 1 minute and 7 days."
        description = message.strip()[reminder_match.start(2):]
        reminder_id = store.add_reminder(minutes, description)
        return f"Reminder {reminder_id} set locally for {minutes} minute(s) from now."
    if text in {"reminders", "pending reminders"}:
        items = store.pending_reminders() if store else []
        return "No pending reminders." if not items else "Pending reminders:\n" + "\n".join(f"{i}. {due} | {value}" for i, due, value in items)
    if text in {"warnings", "warning status", "alerts"}:
        result = warning_snapshot(config=config, project_root=project_root)
        return "No active local warnings." if not result["warnings"] else "Warnings:\n" + "\n".join(result["warnings"])
    if text in {"export report", "export diagnostics", "diagnostics report"}:
        path = export_diagnostics(config=config, project_root=project_root)
        if store:
            store.audit("diagnostics_exported", path.name)
        return f"Diagnostics exported locally to {path}."
    if text in {"roadmap", "checklist", "project roadmap", "setup checklist"}:
        summary = roadmap_summary(project_root)
        if summary["status"] != "ok":
            return "The canonical roadmap is missing."
        return (
            f"Roadmap: {summary['completed']} completed items and {summary['pending']} pending items. "
            f"Canonical file: {summary['path']}."
        )
    if text in {"next", "next step", "what next", "critical path"}:
        summary = roadmap_summary(project_root)
        steps = summary.get("critical_path", [])
        if not steps:
            return "No critical-path steps are recorded."
        return "Current critical path:\n" + "\n".join(f"{index}. {step}" for index, step in enumerate(steps, 1))
    if text in {"system", "system status", "hardware", "hardware status", "resources"}:
        snapshot = system_snapshot(config=config, project_root=project_root)
        return (
            f"System: {snapshot['cpu_logical_count']} logical CPUs; "
            f"RAM {snapshot['memory_available_gb']} GB available of {snapshot['memory_total_gb']} GB "
            f"({snapshot['memory_load_percent']}% used); disk {snapshot['disk_free_gb']} GB free "
            f"of {snapshot['disk_total_gb']} GB."
        )
    if text in {"git", "git status", "repository", "repository status", "repo status"}:
        snapshot = repository_snapshot(config=config, project_root=project_root)
        state = "clean" if snapshot["clean"] else f"has {snapshot['change_count']} change(s)"
        return f"Repository {snapshot['branch']} and {state}."
    if text in {"uptime", "how long have you been on", "how long are you running"}:
        snapshot = uptime_snapshot(config=config, project_root=project_root)
        return f"Windows uptime is {snapshot['days']} day(s), {snapshot['hours']} hour(s), and {snapshot['minutes']} minute(s)."
    if text in {"storage", "storage health", "ssd", "ssd health", "drive health"}:
        snapshot = storage_snapshot(config=config, project_root=project_root)
        if not snapshot["drives"]:
            return "Windows could not report physical-drive health. No changes were attempted."
        details = "; ".join(
            f"{drive['name']} ({drive['size_gb']} GB, {drive['media_type']}): {drive['health']}"
            for drive in snapshot["drives"]
        )
        return "Physical drives: " + details + "."
    if text in {"backup", "backup status", "recovery", "recovery status"}:
        snapshot = recovery_snapshot(config=config, project_root=project_root)
        if snapshot["backup_count"] == 0:
            return "No local recovery snapshot exists yet. Reopen the GUI to create today's snapshot."
        return (
            f"Recovery: {snapshot['backup_count']} backup(s); latest {snapshot['latest_backup']}; "
            f"integrity {snapshot['integrity']}."
        )
    if text in {"restore drill", "test restore", "verify restore"}:
        snapshot = restore_drill_snapshot(config=config, project_root=project_root)
        if snapshot["status"] != "ok":
            return "Restore drill is waiting because no usable backup is available. Live data was unchanged."
        if store:
            store.audit("restore_drill", str(snapshot["backup"]))
        return (
            f"Restore drill passed using {snapshot['backup']}; integrity {snapshot['integrity']}. "
            "The live database was unchanged."
        )
    if text in {"export memory", "memory export", "export memories"}:
        snapshot = memory_export_snapshot(config=config, project_root=project_root)
        if snapshot["status"] != "ok":
            return "Memory export is waiting because no local database exists."
        if store:
            store.audit("memory_exported", Path(str(snapshot["path"])).name)
        return f"Memory and task records exported locally to {snapshot['path']}. No cloud service was used."
    if text in {"external drive", "usb drive", "10tb drive", "external storage"}:
        snapshot = external_storage_snapshot(config=config, project_root=project_root)
        if not snapshot["drives"]:
            return "No external USB disk is detected. No disk changes were attempted."
        details = "; ".join(
            f"disk {drive['number']} {drive['name']} ({drive['size_tb']} TB, {drive['partition_style']}, {drive['health']})"
            for drive in snapshot["drives"]
        )
        suitable = "A suitable 8+ TB drive is present" if snapshot["suitable_drive_present"] else "No suitable 8+ TB drive is present"
        return f"External storage: {details}. {suitable}. No disk changes were attempted."
    if text.startswith("remember "):
        if store is None:
            return "Local memory is unavailable."
        content = message.strip()[9:].strip()
        return f"Remembered locally as note {store.remember(content)}."
    if text in {"memories", "memory", "what do you remember"}:
        items = store.memories() if store else []
        return "No saved memories yet." if not items else "Saved memories:\n" + "\n".join(f"{i}. {value}" for i, value in items)
    if text in {"memory history", "all memories", "archived memories"}:
        items = store.memory_records() if store else []
        return "No memory history exists." if not items else "Memory history:\n" + "\n".join(
            f"{item['id']}. [{item['status']}] {item['content']}" for item in items
        )
    correction = re.fullmatch(r"request correct memory (\d+)\s*:\s*(.+)", message.strip(), re.IGNORECASE)
    change_action = re.fullmatch(r"request (delete|restore) memory (\d+)", text)
    if correction or change_action:
        if store is None:
            return "Local memory governance is unavailable."
        if correction:
            memory_id = int(correction.group(1))
            action = "correct"
            replacement = correction.group(2)
        else:
            assert change_action is not None
            action = change_action.group(1)
            memory_id = int(change_action.group(2))
            replacement = None
        try:
            change_id, approval_id = store.request_memory_change(
                memory_id=memory_id, action=action, replacement_content=replacement
            )
        except ValueError as exc:
            return f"{exc}. Nothing changed."
        return (
            f"Memory change {change_id} requests {action} for memory {memory_id}; approval {approval_id} "
            "is waiting. The memory is unchanged."
        )
    if text in {"memory changes", "pending memory changes"}:
        items = store.memory_changes(pending_only=True) if store else []
        if not items:
            return "No memory changes are awaiting review."
        return "Pending memory changes:\n" + "\n".join(
            f"{item['id']}. {item['action']} memory {item['memory_id']} | approval "
            f"{item['approval_id']} {item['approval_status']}"
            for item in items
        )
    apply_change = re.fullmatch(r"apply memory change (\d+)", text)
    if apply_change:
        if store is None:
            return "Local memory governance is unavailable."
        try:
            result = store.apply_memory_change(int(apply_change.group(1)))
        except ValueError as exc:
            return f"{exc}. Nothing changed."
        return (
            f"Memory change {result['change_id']} applied: {result['action']} memory "
            f"{result['memory_id']}. This was a recoverable soft change; no record was hard-deleted."
        )
    if text.startswith("add task "):
        if store is None:
            return "Local tasks are unavailable."
        description = message.strip()[9:].strip()
        task_id = store.add_task(description)
        return f"Added task {task_id}: {description}. Tasks are records only and never run automatically."
    if text in {"tasks", "task list", "what are we working on"}:
        items = store.pending_tasks() if store else []
        return "No pending tasks." if not items else "Pending tasks:\n" + "\n".join(f"{i}. {value}" for i, value in items)
    if text.startswith("complete task "):
        if store is None:
            return "Local tasks are unavailable."
        raw_id = text.removeprefix("complete task ").strip()
        if not raw_id.isdigit():
            return "Please use a task number, such as 'complete task 1'."
        return f"Task {raw_id} marked complete." if store.complete_task(int(raw_id)) else f"Pending task {raw_id} was not found."
    if "health" in text or "diagnostic" in text:
        result = health_check(config=config, project_root=project_root)
        checks = result["checks"]
        return (
            f"Health is {result['status']}. Python {result['python']}; "
            f"{result['disk_free_gb']} GB free; Git available: {checks['git_available']}."
        )
    if "provider" in text or "cloud" in text or "spend" in text:
        status = provider_status(config)
        lock = "UNLOCKED" if status["cloud_calls_allowed"] else "LOCKED OFF"
        return (
            f"Cloud spending is {lock}. OpenAI configured: {status['openai']['configured']}; "
            f"Gemini configured: {status['gemini']['configured']}."
        )
    if "tool" in text:
        return "Allowed tools: " + ", ".join(available_tools()) + "."
    if "time" in text:
        return "Local time is " + datetime.now().astimezone().strftime("%A, %B %d, %Y at %I:%M %p %Z") + "."
    if text in {"hello", "hi", "hey", "hello josie", "hi josie"}:
        return "Hello, Dustin. I'm online locally. Type 'help' to see what I can do safely."
    return (
        "I don't have that local skill yet. I have not sent your request to a cloud model. "
        "Type 'help' for my current commands."
    )


class JosieApp:
    def __init__(self, root: tk.Tk, *, config: Config, project_root: Path) -> None:
        self.root = root
        self.config = config
        self.project_root = project_root
        self.store = LocalStore(project_root / "data" / "josie.db")
        self.store.create_daily_backup(project_root / "data" / "backups")
        if config.external_storage and config.external_storage.is_dir():
            self.store.create_daily_backup(config.external_storage / "backups" / "josie-database")
        root.title("Josie 1.0")
        root.geometry("900x620")
        root.minsize(700, 480)
        root.configure(bg="#10151c")

        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("Panel.TFrame", background="#18212b")
        style.configure("Title.TLabel", background="#10151c", foreground="#79d7ff", font=("Segoe UI", 22, "bold"))
        style.configure("Status.TLabel", background="#18212b", foreground="#d8e6ef", font=("Segoe UI", 10))
        style.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=8)

        header = ttk.Frame(root, style="Panel.TFrame", padding=14)
        header.pack(fill="x", padx=14, pady=(14, 8))
        ttk.Label(header, text="JOSIE 1.0", style="Title.TLabel").pack(side="left")
        self.health_label = ttk.Label(header, style="Status.TLabel")
        self.health_label.pack(side="right")

        quick_bar = ttk.Frame(root, style="Panel.TFrame", padding=(10, 8))
        quick_bar.pack(fill="x", padx=14, pady=(0, 6))
        for label, command in (
            ("Status", "status"),
            ("System", "system status"),
            ("SSD", "storage health"),
            ("Tasks", "tasks"),
            ("Approvals", "approvals"),
            ("Backups", "backup status"),
            ("Activity", "activity"),
            ("Warnings", "warnings"),
            ("Ledger", "ledger"),
        ):
            ttk.Button(
                quick_bar,
                text=label,
                command=lambda value=command: self._run_quick_command(value),
            ).pack(side="left", padx=3)

        self.transcript = tk.Text(
            root, bg="#0b0f14", fg="#d8e6ef", insertbackground="white", relief="flat",
            wrap="word", font=("Segoe UI", 11), padx=16, pady=14, state="disabled", height=8
        )
        self.transcript.tag_configure("user", foreground="#79d7ff", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_configure("josie", foreground="#8ef0b5", font=("Segoe UI", 11, "bold"))

        side_panel = ttk.Notebook(root, width=260)
        side_panel.pack(side="right", fill="y", padx=(0, 14), pady=8)
        approvals_tab = ttk.Frame(side_panel, style="Panel.TFrame", padding=8)
        activity_tab = ttk.Frame(side_panel, style="Panel.TFrame", padding=8)
        side_panel.add(approvals_tab, text="Approvals")
        side_panel.add(activity_tab, text="Activity")
        self.approval_list = tk.Listbox(approvals_tab, width=34, bg="#0b0f14", fg="#d8e6ef", relief="flat")
        self.approval_list.pack(fill="both", expand=True)
        approval_buttons = ttk.Frame(approvals_tab, style="Panel.TFrame")
        approval_buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(approval_buttons, text="Approve", command=lambda: self._decide_selected("approved")).pack(side="left")
        ttk.Button(approval_buttons, text="Deny", command=lambda: self._decide_selected("denied")).pack(side="right")
        self.activity_list = tk.Listbox(activity_tab, width=34, bg="#0b0f14", fg="#d8e6ef", relief="flat")
        self.activity_list.pack(fill="both", expand=True)

        entry_bar = ttk.Frame(root, style="Panel.TFrame", padding=10)
        entry_bar.pack(side="bottom", fill="x", padx=14, pady=(8, 14))
        self.entry = tk.Entry(entry_bar, bg="#111820", fg="white", insertbackground="white", relief="flat", font=("Segoe UI", 12))
        self.entry.pack(side="left", fill="x", expand=True, ipady=9, padx=(0, 8))
        self.entry.bind("<Return>", self._submit)
        ttk.Button(entry_bar, text="Send", style="Accent.TButton", command=self._submit).pack(side="right")

        self.transcript.pack(fill="both", expand=True, padx=14, pady=8)

        self.refresh_status()
        history = self.store.recent_messages()
        if history:
            for speaker, content in history:
                self._append(speaker, content, "user" if speaker == "You" else "josie", persist=False)
        else:
            self._append("Josie", "I'm online locally. Cloud spending is locked off. Type 'help' to begin.", "josie")
        self.entry.focus_set()
        self._last_warning_signature: tuple[str, ...] | None = None
        self.root.after(30_000, self._scheduled_check)

    def refresh_status(self) -> None:
        health = health_check(config=self.config, project_root=self.project_root)
        cloud = provider_status(self.config)
        cloud_text = "CLOUD ON" if cloud["cloud_calls_allowed"] else "CLOUD LOCKED"
        counts = self.store.counts()
        self.health_label.configure(
            text=(
                f"HEALTH: {health['status'].upper()}   |   TASKS: {counts['pending_tasks']}   |   "
                f"APPROVALS: {counts['pending_approvals']}   |   {cloud_text}"
            )
        )
        self.approval_list.delete(0, "end")
        for approval_id, description in self.store.pending_approvals():
            self.approval_list.insert("end", f"{approval_id}: {description}")
        self.activity_list.delete(0, "end")
        for when, event, detail in self.store.recent_activity(20):
            self.activity_list.insert("end", f"{event}: {detail}")

    def _append(self, speaker: str, message: str, tag: str, *, persist: bool = True) -> None:
        self.transcript.configure(state="normal")
        self.transcript.insert("end", f"{speaker}: ", tag)
        self.transcript.insert("end", message + "\n\n")
        self.transcript.configure(state="disabled")
        self.transcript.see("end")
        if persist:
            self.store.add_message(speaker, message)

    def _submit(self, _event: object | None = None) -> None:
        message = self.entry.get().strip()
        if not message:
            return
        self.entry.delete(0, "end")
        self._append("You", message, "user")
        answer = respond(message, config=self.config, project_root=self.project_root, store=self.store)
        self._append("Josie", answer, "josie")
        self.refresh_status()

    def _run_quick_command(self, command: str) -> None:
        self._append("You", command, "user")
        answer = respond(command, config=self.config, project_root=self.project_root, store=self.store)
        self._append("Josie", answer, "josie")
        self.refresh_status()
        self.entry.focus_set()

    def _decide_selected(self, decision: str) -> None:
        selection = self.approval_list.curselection()
        if not selection:
            return
        raw = self.approval_list.get(selection[0])
        approval_id = int(raw.split(":", 1)[0])
        changed = self.store.decide_approval(approval_id, decision)
        if changed:
            self._append("Josie", f"Approval {approval_id} marked {decision}. No action was executed.", "josie")
        self.refresh_status()

    def _scheduled_check(self) -> None:
        for reminder_id, description in self.store.deliver_due_reminders():
            self._append("Josie", f"Reminder {reminder_id}: {description}", "josie")
        warnings = warning_snapshot(config=self.config, project_root=self.project_root)
        self.store.audit("scheduled_health_check", warnings["status"])
        signature = tuple(warnings["warnings"])
        if warnings["warnings"] and signature != self._last_warning_signature:
            self._append("Josie", "Warning: " + "; ".join(warnings["warnings"]), "josie")
        elif not warnings["warnings"] and self._last_warning_signature:
            self._append("Josie", "All monitored warnings have cleared.", "josie")
        self._last_warning_signature = signature
        self.refresh_status()
        self.root.after(300_000, self._scheduled_check)


def launch_gui(*, config: Config, project_root: Path) -> None:
    root = tk.Tk()
    JosieApp(root, config=config, project_root=project_root)
    root.mainloop()
