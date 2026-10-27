# MaiBot Android Lite Core

把 MaiBot 的**聊天核心**剥离成一个可嵌入 Android 应用的、无 proot 依赖的 Python 包。

> 本仓库是 [MaiBot](https://github.com/MaiM-with-u/MaiBot) 1.3.15 的派生分支，
> 目标场景是**单用户单会话**的嵌入式助手，不是原版的群聊/多租户机器人。

---

## 为什么要做这个分支

上游 MaiBot 依赖 61 个原生扩展（`scipy` 94MB、`pyarrow` 136MB、`pandas` 52MB、
`faiss` 26MB、Chromium 128MB……），这些在 Android bionic 上**几乎都拿不到 wheel**，
只能用 proot 容器跑 glibc 版本。

用户明确不需要：
- 插件系统（运行时 `pip install` + 多进程 Runner）
- WebUI / 管理面板
- 多租户、群聊、记忆隔离
- A_memorix 长期记忆
- 外接 Agent / ACP

把这些砍掉之后，核心链路的原生依赖降到 **10 个**，全部在 aarch64 上可得。

---

## 实测数据

| 指标 | 上游全功能 | 本分支 |
|---|---|---|
| 第三方原生扩展 | **61** | **10** |
| site-packages 体积 | 786 MB | 见 CI 汇总 |
| `scipy` / `pandas` / `pyarrow` / `faiss` | 必需 | 完全移除 |
| `fastapi` / `uvicorn` / `starlette` | 必需 | 完全移除 |
| 需要 proot | 是 | **否** |

保留下来的 10 个原生扩展（均为 aarch64 可得）：

```
numpy  pydantic_core  sqlalchemy(greenlet)  pillow
msgpack  rapidfuzz  watchfiles  zstandard  rpds-py  cryptography
```

---

## 关键改动

### 1. `src/common/optional_features.py`（新增）

把已禁用子系统的**模块级硬导入**改为延迟导入 + 空实现：

| 原文件 | 原行为 |
|---|---|
| `src/services/memory_service.py` | 模块导入期就 `from src.A_memorix.host_service import ...` |
| `src/services/memory_flow_service.py` | 同上，另加图片组件辅助 |
| `src/services/person_fact_reverification.py` | 同上 |
| `src/maisaka/builtin_tool/query_image_memory.py` | 同上 |
| `src/maisaka/memory/image_injector.py` | 同上 |
| `src/maisaka/memory/person_profile.py` | `from src.A_memorix.core.utils.profile_text import ...` |
| `src/maisaka/runtime.py` | `from src.agent.provider import AgentToolProvider` |

**为什么这是必须的**：即使 `config/bot_config.toml` 里 `a_memorix.plugin.enabled = false`，
这些模块级导入仍会在导入期把 `scipy` 拉进来。导入链是：

```
bot.py → heartflow_message_processor → heartflow_manager
  → maisaka/runtime → chat/utils/utils → person_info
  → memory_service → A_memorix → scipy
```

### 2. `src/common/maim_lite.py`（新增）

`maim_message/__init__.py` 把数据模型和 WebSocket 服务端绑在一起：

```python
from .api import MessageClient, MessageServer        # → uvicorn → fastapi
from .message_base import Seg, MessageBase, ...      # ← 我们只要这些
```

这导致**任何使用 `MessageBase` 的进程都会被拖入整条 Web 栈**。

解法：在 `src/__init__.py` 里预置一个"空壳" `maim_message` 包（带正确 `__path__`），
使 `import maim_message.message_base` 不执行原始 `__init__.py`。
这是 `import src` 时自动完成的，无需调用方配合。

同时把核心路径上的 6 处 `from maim_message import X` 改为
`from maim_message.message_base import X`（或 `.converter`）。

### 3. `requirements-lite.txt`（新增）

精简依赖清单。移除项及原因见文件内注释。

### 4. `scripts/check_lite_core.py`（新增）

**CI 门禁**。若上游合并把重依赖重新引入核心导入链，构建会失败：

- 用 `sys.meta_path` 拦截器模拟"这些包在目标平台不可用"
- 断言：核心入口可导入、shim 已生效、零重依赖泄漏、原生扩展在白名单内

---

## 本地验证

```bash
python -m venv .venv && . .venv/bin/activate
grep -v '^maim-message' requirements-lite.txt > /tmp/req.txt
pip install -r /tmp/req.txt
pip install --no-deps 'maim-message==0.6.8'

python scripts/check_lite_core.py --strict
```

期望输出：

```
[lite-core] 已加载第三方原生扩展 (11): ['PIL', 'greenlet', 'mmap', ...]
[lite-core] 门禁通过：核心链路无重依赖。
```

---

## CI

`.github/workflows/lite-core.yml`：

1. **gate** —— 在干净环境装精简依赖，跑门禁 + 静态扫描
2. **wheels** —— 用 `manylinux_2_28_aarch64` 容器交叉编译 10 个原生扩展
   （`cryptography` 额外装 Rust 工具链），产出 wheel artifact
3. **summarize** —— 汇总 wheel 体积，写进 job summary，用于评估 APK 增量

wheel 可用于 Chaquopy 的 `sourceDir` 离线安装，或 Termux 的本地 pip 源。

---

## 待办

- [ ] 把 `chat_bot.message_process` 接成 Android 侧的入口（替代 maim_message 的 WebSocket 服务端）
- [ ] 写一个最小的 `LiteRuntime`：不启动 WebUI / plugin_runtime / API server，只跑消息处理
- [ ] 多租户 / 记忆隔离相关代码的进一步裁剪（`session_id` 简化）
- [ ] Chaquopy 侧确认 CPython 3.12 支持情况
- [ ] 实测瘦身后的启动耗时与 RSS

---

## 与上游的关系

保持与上游 `src/` 目录结构一致，改动集中在**导入层的剥离**，不重写业务逻辑。
升级上游版本时，优先复用 `optional_features.py` / `maim_lite.py`，
只处理新增的模块级硬导入（门禁脚本会指出来）。
