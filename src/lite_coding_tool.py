"""规划模型控制 Coding Agent 会话的受限宿主工具。"""

from typing import Any, Dict, List, Optional

import json

from src.core.tooling import (
    ToolAvailabilityContext,
    ToolExecutionContext,
    ToolExecutionResult,
    ToolInvocation,
    ToolProvider,
    ToolSpec,
)

_controller: Any = None


def configure_host_controller(controller: Any) -> None:
    """由 Android 桥注入宿主控制器；None 表示不提供该工具。"""

    global _controller
    _controller = controller


def get_read_file_spec() -> ToolSpec:
    return ToolSpec(
        name="context_read_file",
        description=(
            "只为补充上下文或核验 Coding Agent 成果而读取文件，不是用来替用户完成任务的执行工具。"
            "只能读取附件目录或当前工作区内文件，单次最多 1MB。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {"path": {"type": "string", "description": "要核验的文件路径。"}},
            "required": ["path"],
        },
        provider_name="coda_android",
        provider_type="builtin",
    )


def get_terminal_spec() -> ToolSpec:
    return ToolSpec(
        name="context_run_terminal",
        description=(
            "只在当前工作区运行只读检查命令，用于核验 Coding Agent 的成果或补充上下文。"
            "不得用它直接替用户完成开发任务，不得执行破坏性命令、后台常驻服务或交互式程序。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "例如 git diff、grep、测试命令。"},
                "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 30},
            },
            "required": ["command"],
        },
        provider_name="coda_android",
        provider_type="builtin",
    )


def get_tool_spec() -> ToolSpec:
    """声明只包含会话生命周期的控制动作。"""

    return ToolSpec(
        name="coding_agent",
        description=(
            "控制本机 Coding Agent 会话。create 新建编码会话，send 向当前编码会话发送任务，"
            "stop 停止当前生成，close 关闭当前编码会话。不会执行任意 Shell。"
        ),
        parameters_schema={
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "send", "stop", "close"]},
                "text": {"type": "string", "description": "action=send 时发送的任务文本。"},
            },
            "required": ["action"],
        },
        provider_name="coda_android",
        provider_type="builtin",
    )


class CodingAgentToolProvider(ToolProvider):
    """只向规划模型暴露 Coding Agent 会话边界。"""

    provider_name = "coda_android"
    provider_type = "builtin"

    async def list_tools(
        self,
        context: Optional[ToolAvailabilityContext] = None,
    ) -> List[ToolSpec]:
        return (
            [get_tool_spec(), get_read_file_spec(), get_terminal_spec()]
            if _controller is not None
            else []
        )

    async def invoke(
        self,
        invocation: ToolInvocation,
        context: Optional[ToolExecutionContext] = None,
    ) -> ToolExecutionResult:
        del context
        if _controller is None:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message="当前宿主没有 Coding Agent 控制器。",
            )
        if invocation.tool_name == "context_read_file":
            try:
                payload = json.loads(str(_controller.readFile(str(invocation.arguments.get("path") or ""))))
            except Exception as exc:
                return ToolExecutionResult(
                    tool_name=invocation.tool_name, success=False, error_message=str(exc)
                )
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=bool(payload.get("ok")),
                content=str(payload.get("content") or payload.get("message") or ""),
                error_message=None if payload.get("ok") else str(payload.get("message") or "读取失败"),
            )
        if invocation.tool_name == "context_run_terminal":
            try:
                payload = json.loads(
                    str(
                        _controller.runTerminal(
                            str(invocation.arguments.get("command") or ""),
                            int(invocation.arguments.get("timeout_seconds") or 20),
                        )
                    )
                )
            except Exception as exc:
                return ToolExecutionResult(
                    tool_name=invocation.tool_name, success=False, error_message=str(exc)
                )
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=bool(payload.get("ok")),
                content=str(payload.get("output") or payload.get("message") or ""),
                error_message=None if payload.get("ok") else str(payload.get("message") or "命令失败"),
            )
        action = str(invocation.arguments.get("action") or "").strip().lower()
        text = str(invocation.arguments.get("text") or "").strip()
        if action not in {"create", "send", "stop", "close"}:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=f"不支持的 Coding Agent 动作：{action}",
            )
        if action == "send" and not text:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message="action=send 需要 text。",
            )
        try:
            response: Dict[str, Any] = json.loads(str(_controller.controlSession(action, text)))
        except Exception as exc:
            return ToolExecutionResult(
                tool_name=invocation.tool_name,
                success=False,
                error_message=str(exc),
            )
        ok = bool(response.get("ok"))
        message = str(response.get("message") or ("完成" if ok else "操作失败"))
        return ToolExecutionResult(
            tool_name=invocation.tool_name,
            success=ok,
            content=message,
            error_message=None if ok else message,
        )

    async def close(self) -> None:
        return None


def get_provider() -> CodingAgentToolProvider:
    return CodingAgentToolProvider()