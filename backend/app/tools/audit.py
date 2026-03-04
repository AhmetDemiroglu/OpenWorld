from __future__ import annotations

import asyncio
import inspect
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Tuple

from ..agent import AgentService
from ..config import settings
from ..memory import SessionStore
from .registry import TOOLS, execute_tool

_DATA_ROOT = settings.workspace_path.resolve()
_AUDIT_DIR = (_DATA_ROOT / "audit").resolve()
_SESSIONS_DIR = (_DATA_ROOT / "sessions").resolve()


SAFE_PROBES: Dict[str, Dict[str, Any]] = {
    "get_system_info": {},
    "list_processes": {"limit": 5},
    "network_info": {},
    "list_directory": {"path": "."},
    "create_folder": {"folder_path": "audit/tmp_folder"},
    "write_file": {"path": "audit/tmp_folder/probe.txt", "content": "audit probe"},
    "read_file": {"path": "audit/tmp_folder/probe.txt"},
    "search_files": {"path": "audit", "pattern": "probe"},
    "create_markdown_report": {"title": "Audit Probe", "content": "Probe content"},
    "list_tasks": {},
    "list_calendar_events": {},
    "search_news": {"query": "turkiye gundem", "limit": 3},
}

# These tools may fail in normal environments (missing creds, blocked network, etc.)
DEGRADED_OK_TOOLS = {
    "check_gmail_messages",
    "check_outlook_messages",
    "search_news",
    "fetch_web_page",
}

# Tools that are high-impact, interactive, destructive, hardware-dependent, or noisy.
SKIPPED_BY_DEFAULT = {
    "delete_file",
    "move_file",
    "copy_file",
    "kill_process",
    "shutdown_system",
    "lock_workstation",
    "execute_command",
    "click_on_screen",
    "type_text",
    "press_key",
    "mouse_move",
    "drag_to",
    "scroll",
    "hotkey",
    "alert",
    "confirm",
    "prompt",
    "webcam_capture",
    "webcam_record_video",
    "list_cameras",
    "start_audio_recording",
    "stop_audio_recording",
    "play_audio",
    "text_to_speech",
    "screenshot_desktop",
    "screenshot_webpage",
    "find_image_on_screen",
    "ocr_screenshot",
    "ocr_image",
    "open_in_vscode",
    "open_folder",
    "activate_window",
    "minimize_all_windows",
    "eject_usb_drive",
}


def _fn_required_params(fn: Any) -> List[str]:
    required: List[str] = []
    sig = inspect.signature(fn)
    for name, param in sig.parameters.items():
        if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
            continue
        if param.default is inspect._empty:
            required.append(name)
    return required


def _validate_registry_specs() -> Dict[str, Any]:
    issues: List[Dict[str, Any]] = []
    per_tool: Dict[str, Dict[str, Any]] = {}

    for key, (fn, spec) in TOOLS.items():
        tool_issues: List[str] = []
        if not callable(fn):
            tool_issues.append("tool function is not callable")

        spec_type = spec.get("type")
        function_block = spec.get("function", {})
        spec_name = function_block.get("name")
        parameters = function_block.get("parameters", {})
        props = parameters.get("properties", {}) if isinstance(parameters, dict) else {}
        required = parameters.get("required", []) if isinstance(parameters, dict) else []

        if spec_type != "function":
            tool_issues.append(f"spec.type must be 'function', got: {spec_type!r}")
        if spec_name != key:
            tool_issues.append(f"spec function name mismatch: key={key!r}, spec={spec_name!r}")
        if not isinstance(props, dict):
            tool_issues.append("parameters.properties must be a dict")
            props = {}
        if required and not isinstance(required, list):
            tool_issues.append("parameters.required must be a list when present")
            required = []

        fn_required = _fn_required_params(fn)
        missing_required_in_spec = [p for p in fn_required if p not in props]
        invalid_required = [p for p in required if p not in props]

        if missing_required_in_spec:
            tool_issues.append(f"function required params missing in spec: {missing_required_in_spec}")
        if invalid_required:
            tool_issues.append(f"spec.required has unknown props: {invalid_required}")

        per_tool[key] = {
            "function_required": fn_required,
            "spec_properties": sorted(props.keys()),
            "spec_required": required,
            "issue_count": len(tool_issues),
        }
        for item in tool_issues:
            issues.append({"tool": key, "type": "spec", "message": item})

    return {
        "total_tools": len(TOOLS),
        "issues": issues,
        "per_tool": per_tool,
    }


def _run_safe_probes() -> Dict[str, Any]:
    _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    preseed = _AUDIT_DIR / "tmp_folder" / "probe.txt"
    preseed.parent.mkdir(parents=True, exist_ok=True)
    preseed.write_text("audit probe", encoding="utf-8")
    results: List[Dict[str, Any]] = []

    for name in sorted(TOOLS.keys()):
        if name in SKIPPED_BY_DEFAULT:
            results.append({"tool": name, "status": "skipped", "reason": "high-impact or interactive"})
            continue
        if name not in SAFE_PROBES:
            results.append({"tool": name, "status": "skipped", "reason": "no safe probe configured"})
            continue

        args = SAFE_PROBES[name]
        try:
            output = execute_tool(name, args)
            if not isinstance(output, dict):
                results.append({"tool": name, "status": "fail", "reason": "non-dict tool output"})
                continue

            if output.get("error"):
                if name in DEGRADED_OK_TOOLS:
                    results.append({"tool": name, "status": "degraded", "error": str(output.get("error"))[:400]})
                else:
                    results.append({"tool": name, "status": "fail", "error": str(output.get("error"))[:400]})
            else:
                results.append({"tool": name, "status": "pass"})
        except Exception as exc:  # noqa: BLE001
            tb = traceback.format_exc(limit=2)
            results.append(
                {
                    "tool": name,
                    "status": "exception",
                    "error": str(exc)[:300],
                    "trace": tb[:1000],
                }
            )

    counts = {
        "pass": sum(1 for x in results if x["status"] == "pass"),
        "degraded": sum(1 for x in results if x["status"] == "degraded"),
        "fail": sum(1 for x in results if x["status"] == "fail"),
        "exception": sum(1 for x in results if x["status"] == "exception"),
        "skipped": sum(1 for x in results if x["status"] == "skipped"),
    }
    return {"counts": counts, "results": results}


def _run_agent_behavior_checks() -> Dict[str, Any]:
    checks: List[Dict[str, Any]] = []

    class _UnavailableLLM:
        async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {"message": {"role": "assistant", "content": "Mevcut arac yok."}}

    class _ProcessStartLLM:
        async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {
                "message": {
                    "role": "assistant",
                    "content": '{"command":"create_markdown_report","title":"Audit","content":"ok","status":"process_start"}',
                }
            }

    class _WrongToolThenStopLLM:
        def __init__(self) -> None:
            self.calls = 0

        async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
            self.calls += 1
            if self.calls == 1:
                return {
                    "message": {
                        "role": "assistant",
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "audit_tc_1",
                                "function": {"name": "webcam_capture", "arguments": "{}"},
                            }
                        ],
                    }
                }
            return {"message": {"role": "assistant", "content": "Mail kontrolu denemesi bitti."}}

    class _NoToolHallucinationLLM:
        async def chat(self, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]]) -> Dict[str, Any]:
            return {"message": {"role": "assistant", "content": "Genel bir haber ozeti veriyorum."}}

    async def _run_case(llm_obj: Any, session_id: str, prompt: str) -> Tuple[str, int, List[str]]:
        store = SessionStore(_SESSIONS_DIR)
        agent = AgentService(store)
        agent.llm = llm_obj
        reply, steps, used_tools, _ = await agent.run(session_id, prompt)
        return reply, steps, used_tools

    def _run_coro_sync(coro: Any) -> Any:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)

        holder: Dict[str, Any] = {}

        def _worker() -> None:
            try:
                holder["result"] = asyncio.run(coro)
            except Exception as exc:  # noqa: BLE001
                holder["error"] = exc

        t = threading.Thread(target=_worker, daemon=True)
        t.start()
        t.join()
        if "error" in holder:
            raise holder["error"]
        return holder.get("result")

    try:
        reply, steps, used_tools = _run_coro_sync(
            _run_case(_UnavailableLLM(), "audit_unavailable_case", "hata raporu olustur")
        )
        checks.append(
            {
                "name": "fallback_from_unavailable_claim",
                "status": "pass" if ("create_markdown_report" in used_tools and "Islem tamamlandi" in reply) else "fail",
                "details": {"steps": steps, "used_tools": used_tools, "reply_head": reply[:160]},
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "fallback_from_unavailable_claim", "status": "exception", "error": str(exc)})

    try:
        reply, steps, used_tools = _run_coro_sync(
            _run_case(_ProcessStartLLM(), "audit_process_start_case", "rapor olustur")
        )
        checks.append(
            {
                "name": "no_half_finished_process_start",
                "status": "pass" if ("create_markdown_report" in used_tools and "Islem tamamlandi" in reply) else "fail",
                "details": {"steps": steps, "used_tools": used_tools, "reply_head": reply[:160]},
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "no_half_finished_process_start", "status": "exception", "error": str(exc)})

    try:
        reply, steps, used_tools = _run_coro_sync(
            _run_case(_WrongToolThenStopLLM(), "audit_wrong_tool_scope_case", "mail kontrolu yap")
        )
        checks.append(
            {
                "name": "wrong_tool_scope_blocked",
                "status": "pass" if "webcam_capture" not in used_tools else "fail",
                "details": {"steps": steps, "used_tools": used_tools, "reply_head": reply[:160]},
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "wrong_tool_scope_blocked", "status": "exception", "error": str(exc)})

    try:
        reply, steps, used_tools = _run_coro_sync(
            _run_case(_NoToolHallucinationLLM(), "audit_force_tool_case", "gunun haber basliklarini cikar")
        )
        checks.append(
            {
                "name": "force_tool_on_actionable_intent",
                "status": "pass" if "search_news" in used_tools and "Islem tamamlandi" in reply else "fail",
                "details": {"steps": steps, "used_tools": used_tools, "reply_head": reply[:160]},
            }
        )
    except Exception as exc:  # noqa: BLE001
        checks.append({"name": "force_tool_on_actionable_intent", "status": "exception", "error": str(exc)})

    counts = {
        "pass": sum(1 for c in checks if c["status"] == "pass"),
        "fail": sum(1 for c in checks if c["status"] == "fail"),
        "exception": sum(1 for c in checks if c["status"] == "exception"),
    }
    return {"counts": counts, "checks": checks}


def run_tools_audit(run_probes: bool = True) -> Dict[str, Any]:
    spec_report = _validate_registry_specs()
    probe_report: Dict[str, Any] = {"counts": {}, "results": []}
    behavior_report: Dict[str, Any] = {"counts": {}, "checks": []}
    if run_probes:
        probe_report = _run_safe_probes()
        behavior_report = _run_agent_behavior_checks()

    summary = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "total_tools": spec_report["total_tools"],
        "spec_issue_count": len(spec_report["issues"]),
        "probe_counts": probe_report.get("counts", {}),
        "behavior_counts": behavior_report.get("counts", {}),
    }

    report = {
        "summary": summary,
        "spec": spec_report,
        "probes": probe_report,
        "behavior": behavior_report,
    }

    out_path = _AUDIT_DIR / "tools_audit_latest.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(__import__("json").dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["saved_to"] = str(out_path.resolve())
    return report
