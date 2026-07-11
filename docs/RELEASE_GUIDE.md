# 插件版本发布详细指南（通用）

> 适用范围：**本仓库（MoviePilot-Plugins）内所有 v2 插件**，不限于某个具体插件。下文以 `<插件名>` / `<插件目录>` 作为占位，请替换成实际插件。

本文档是 `AGENTS.md` 中「版本号发布硬性规则」的**详细操作步骤**。每次升版本号都必须执行下面的全部步骤，缺一不可。

## 为什么需要这条规则

MoviePilot 通过根目录 `package.v2.json` 读取插件列表与版本号、展示在插件市场；`__init__.py` 里的 `plugin_version` 是代码内声明的版本；`README.md` 与 `CHANGELOG.md` 是面向用户的说明。四者必须一致，否则会出现「市场显示一个版本、代码实际是另一个版本、更新日志对不上」的混乱。

## 必须更新的 4 个文件及具体改法

以插件目录 `MoviePilot-Plugins/plugins.v2/<插件目录>/` 为例，假设插件名为 `<插件名>`。

### 1. `MoviePilot-Plugins/package.v2.json`（仓库根）

在 `<插件名>` 对应的对象内：

- `version`：改为新版本号，如 `"0.8.0"`
- `description`：若本次新增了可见能力，补充一句话描述
- `history`：在对象内新增一条，键为 `"vX.Y.Z"`，值为本次变更摘要。**注意：`history` 条目要简短写，不要过长——用一两句话概括核心变更即可，详细变更留在各插件自身的 `CHANGELOG.md`**。例如：

```json
"v0.8.0": "列表场景通知补全海报图，每个条目带媒体海报；build_card_v2 与 send_notification 新增 image_items 参数。"
```

> 注意：`history` 中相邻条目之间要有英文逗号，保持合法 JSON。

### 2. `MoviePilot-Plugins/plugins.v2/<插件目录>/README.md`

在插件说明小节下，找到版本行：

```
- **版本**: 0.7.0
```

改为新版本号：

```
- **版本**: 0.8.0
```

### 3. `MoviePilot-Plugins/plugins.v2/<插件目录>/CHANGELOG.md`

在文件顶部（第一个 `##` 之上）新增一个版本小节。该文件是**详细变更日志**所在，可按「新增 / 优化 / 修复 / 说明」分类详细填写（与 `package.v2.json` 的简短 `history` 互补）。版本号写在 `## vX.Y.Z - YYYY-MM-DD` 标题里。

```markdown
## v0.8.0 - 2026-07-09

### 新增
- ...

### 修复
- ...
```

### 4. `MoviePilot-Plugins/plugins.v2/<插件目录>/__init__.py`

在插件类定义顶部，找到：

```python
plugin_version = "0.7.0"
```

改为：

```python
plugin_version = "0.8.0"
```

该值同时用于详情页测试卡片显示的版本号，务必与上面三个文件保持一致。

## 完整示例（以 0.7.0 → 0.8.0 为例）

| 文件 | 改动 |
| --- | --- |
| `package.v2.json`（根） | `<插件名>.version` → `0.8.0`；`history` 加简短 `v0.8.0` |
| `plugins.v2/<插件目录>/README.md` | `**版本**: 0.8.0` |
| `plugins.v2/<插件目录>/CHANGELOG.md` | 顶部加 `## v0.8.0 - 2026-07-09` 详细小节 |
| `plugins.v2/<插件目录>/__init__.py` | `plugin_version = "0.8.0"` |

## 提交前检查清单

- [ ] 四个文件版本号字符串完全一致（如均为 `0.8.0`）
- [ ] `package.v2.json` 仍为合法 JSON（可用 `python -m json.tool package.v2.json` 校验）
- [ ] `package.v2.json` 的 `history` 条目**简短**（一两句话概括核心变更，详细内容在 `CHANGELOG.md`）
- [ ] `CHANGELOG.md` 新版本小节内容完整（新增 / 优化 / 修复 / 说明分类）
- [ ] 没有把 `tasks.md`、`agents_chat/`、`DESIGN.md`、`COMPARISON.md` 等开发文档误加入提交（按仓库规则这些不进 git）
