"""规划模型的 Coding Agent 控制边界测试。"""

from types import SimpleNamespace

import json

import pytest

from src.lite_coding_tool import configure_host_controller, get_provider


class _Host:
    def __init__(self) -> None:
        self.calls = []

    def controlSession(self, action: str, text: str) -> str:
        self.calls.append((action, text))
        return json.dumps({"ok": True, "message": "完成"})


@pytest.mark.asyncio
async def test_coding_agent_tool_is_hidden_without_host() -> None:
    configure_host_controller(None)
    assert await get_provider().list_tools() == []


@pytest.mark.asyncio
async def test_coding_agent_tool_passes_only_session_actions() -> None:
    host = _Host()
    configure_host_controller(host)
    provider = get_provider()
    invocation = SimpleNamespace(tool_name="coding_agent", arguments={"action": "send", "text": "修复构建"})

    result = await provider.invoke(invocation)

    assert result.success
    assert host.calls == [("send", "修复构建")]
    configure_host_controller(None)