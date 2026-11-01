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
        return [get_tool_spec()] if _controller is not None else []

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