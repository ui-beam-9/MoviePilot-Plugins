# AGENTS.md — MoviePilot-Plugins 插件维护与开发规则（通用）

本文件为参与本仓库（MoviePilot-Plugins）各 v2 插件维护与开发的 Agent / 协作者提供**硬性规则**，适用于仓库内所有插件，不限于某一个。

## 开发前必读（硬性规则）

在**新建插件**或**修改任意已有插件**（改代码、改元数据、提交）之前，Agent / 协作者**必须先完整阅读以下文档**，并严格遵循其中的约定与边界。跳过阅读直接动手，是导致版本不一致、插件加载失败、与宿主仓库冲突、违反渲染/配置规范的主要原因。

- [docs/V2_Plugin_Development.md](./docs/V2_Plugin_Development.md) — **V2 插件开发权威指南**：运行模型、版本选择、最小骨架、`_PluginBase` 核心能力、配置/数据/分身兼容、各能力面（远程命令 / 插件 API / 公共服务 / 仪表板 / 工作流 / 模块重载 / 智能体工具）、三种渲染模式（Vuetify JSON、Vue 联邦、侧栏全页入口）、调试与校验、发布清单。改插件代码前以本文件为准。
- [docs/Repository_Guide.md](./docs/Repository_Guide.md) — **仓库指南**：仓库职责、目录结构、`package.json` / `package.v2.json` 元数据字段、版本选择与加载规则、与宿主仓库 / 前端的协作边界、推荐开发流程、校验建议、发布流程。涉及目录落位、元数据、版本加载时以本文件为准。
- [docs/FAQ.md](./docs/FAQ.md) — **常见问题索引**（18 个主题）：扩展消息渠道、远程命令响应、对外暴露 API、注册公共服务、增强识别、扩展索引站点、调用 API、仪表板渲染、探索 / 推荐数据源、模块重载、存储类型、工作流集成、消息交互、系统缓存、智能体工具、侧栏导航、限定宿主版本。遇到具体能力实现时按需查阅对应子文档。
- [docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md) — **版本发布详细步骤**（4 文件同步、`history` 简短）。仅当本次改动涉及升版本号时才需要阅读。

> ⚠️ 以上四条是**硬性开发规则**：动手写代码 / 改元数据 / 提交之前，先把这些文档看一遍。新建插件时四份都要通读；修改已有插件至少重读 V2 指南与仓库指南中相关章节，并视情况查 FAQ。

## 版本号发布硬性规则

每次更新**任意插件**版本号（如 `0.7.0` → `0.8.0`）时，**必须同步修改以下 4 个文件**，保证版本号、描述、版本历史、更新日志完全一致。遗漏任一文件都会导致 MoviePilot 插件市场显示的版本与代码实际版本不一致。以插件 `<插件名>`（目录 `plugins.v2/<插件目录>/`）为例：

1. `MoviePilot-Plugins/package.v2.json`（仓库根，该插件对象内的 `version` 与 `history`）
2. `MoviePilot-Plugins/plugins.v2/<插件目录>/README.md`
3. `MoviePilot-Plugins/plugins.v2/<插件目录>/CHANGELOG.md`
4. `MoviePilot-Plugins/plugins.v2/<插件目录>/__init__.py`（顶部 `plugin_version`）

各文件具体改什么、怎么改，见 [docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md)。

> ⚠️ 易漏点：`package.v2.json` 在仓库根，不在 `plugins.v2/<插件目录>/` 子目录内（子目录没有该文件）。

### package.v2.json 的 history 条目要简短

`history["vX.Y.Z"]` 的值**用一两句话概括核心变更即可，不要过长**；详细变更放在各插件自身的 `CHANGELOG.md`。

## 提交前检查清单

- [ ] `package.v2.json`：该插件 `version` + `description` + `history` 三处已更新
- [ ] `README.md`：插件小节 `**版本**: X.Y.Z` 已更新
- [ ] `CHANGELOG.md`：已新增 `## vX.Y.Z - YYYY-MM-DD` 小节并填写变更
- [ ] `__init__.py`：顶部 `plugin_version = "X.Y.Z"` 已更新
- [ ] 四个文件的版本号字符串完全一致
- [ ] `package.v2.json` 仍为合法 JSON（可用 `python -m json.tool package.v2.json` 校验）

## 版本号约定

- 采用语义化版本 `主.次.修订`
- 新增功能 / 可见能力变化 → 升 `次` 版本（如 `0.7.0` → `0.8.0`）
- 仅修复 bug、无能力变化 → 升 `修订` 版本（如 `0.8.0` → `0.8.1`）

## Commit Message 规范

- **文档改动不混入功能提交**：「文档内容」范围包括 `AGENTS.md`、`docs/` 目录下的通用文档，以及各插件自身的 `README.md` / `CHANGELOG.md` 与 `package.v2.json` 中的 `version`、`history` 段落。这些文档改动**不混入功能（`feat:` / `fix:` 等）提交**；功能提交只含代码变更（如 `__init__.py`）。文档变更留作本地或单独处理，本仓库（MoviePilot-Plugins）默认不单独建 `docs:` commit。
- **标题与内容不含版本号**：commit message 的标题和正文**不要出现版本号**（如 `0.9.1`、`v0.9.1`）。版本号由 `package.v2.json` / `CHANGELOG.md` / `__init__.py` 等文件承载，提交说明里无需重复，避免版本号在 message 与文件之间再次出现不一致。
- 标题与正文格式遵循仓库约定的 `<类型>: <描述>` / `<类型>(<插件名>): <描述>`，详见用户级自定义指令中的通用 commit 模板（含「问题根因 / 修复内容」结构）。

## 相关文档

- V2 插件开发权威指南（新建 / 修改插件前必读）：[docs/V2_Plugin_Development.md](./docs/V2_Plugin_Development.md)
- 仓库职责 / 目录 / 元数据 / 版本加载 / 协作边界：[docs/Repository_Guide.md](./docs/Repository_Guide.md)
- 常见问题索引（按能力主题查阅）：[docs/FAQ.md](./docs/FAQ.md)
- 版本发布详细步骤与示例（通用）：[docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md)
