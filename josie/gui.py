"""Lightweight local GUI for Josie 1.0."""

from __future__ import annotations

import json
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk

from .config import Config
from .diagnostics import health_check, repository_snapshot, system_snapshot
from .providers import provider_status
from .storage import LocalStore
from .tools import available_tools


def respond(message: str, *, config: Config, project_root: Path, store: LocalStore | None = None) -> str:
    """Handle a deliberately small, local-only conversational command set."""
    text = message.strip().lower()
    if not text:
        return "Please type a request."
    if text in {"help", "?", "commands"} or "what can you do" in text:
        return (
            "I can check health, show cloud status, list allowed tools, report the time, remember notes, "
            "and manage tasks. Try: 'remember ...', 'memories', 'add task ...', 'tasks', or "
            "'complete task 1'. Cloud calls are locked off."
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
    if text.startswith("remember "):
        if store is None:
            return "Local memory is unavailable."
        content = message.strip()[9:].strip()
        return f"Remembered locally as note {store.remember(content)}."
    if text in {"memories", "memory", "what do you remember"}:
        items = store.memories() if store else []
        return "No saved memories yet." if not items else "Saved memories:\n" + "\n".join(f"{i}. {value}" for i, value in items)
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

        self.transcript = tk.Text(
            root, bg="#0b0f14", fg="#d8e6ef", insertbackground="white", relief="flat",
            wrap="word", font=("Segoe UI", 11), padx=16, pady=14, state="disabled", height=8
        )
        self.transcript.tag_configure("user", foreground="#79d7ff", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_configure("josie", foreground="#8ef0b5", font=("Segoe UI", 11, "bold"))

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


def launch_gui(*, config: Config, project_root: Path) -> None:
    root = tk.Tk()
    JosieApp(root, config=config, project_root=project_root)
    root.mainloop()
