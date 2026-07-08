# LarkMessager 版本发布详细指南

本文档是 `AGENTS.md` 中「版本号发布硬性规则」的**详细操作步骤**。每次升版本号都必须执行下面的全部步骤，缺一不可。

## 为什么需要这条规则

MoviePilot 通过 `package.v2.json` 读取插件列表与版本号、展示在插件市场；`__init__.py` 里的 `plugin_version` 是代码内声明的版本；`README.md` 与 `CHANGELOG.md` 是面向用户的说明。四者必须一致，否则会出现「市场显示一个版本、代码实际是另一个版本、更新日志对不上」的混乱。

## 必须更新的 4 个文件及具体改法

### 1. `MoviePilot-Plugins/package.v2.json`

在 `LarkMessager` 对象内：

- `version`：改为新版本号，如 `"0.8.0"`
- `description`：若本次新增了可见能力，补充一句话描述（如「列表类通知支持海报图文展示」）
- `history`：在对象内新增一条，键为 `"vX.Y.Z"`，值为本次变更摘要。例如：

```json
"v0.8.0": "列表场景通知补全海报图：媒体选择列表与资源选择列表从纯文字改为图文卡片……"
```

> 注意：`history` 中相邻条目之间要有英文逗号，保持合法 JSON。

### 2. `MoviePilot-Plugins/README.md`

在 `### LarkMessager - Lark 应用消息通知` 小节下，找到：

```
- **版本**: 0.7.0
```

改为新版本号：

```
- **版本**: 0.8.0
```

### 3. `MoviePilot-Plugins/plugins.v2/larkmessager/CHANGELOG.md`

在文件顶部（第一个 `##` 之上）新增一个版本小节。该文件**只更新版本号**（即新增对应版本号的章节），无需维护独立的「当前版本」字段——版本号就写在 `## vX.Y.Z - YYYY-MM-DD` 标题里。

```markdown
## v0.8.0 - 2026-07-09

### 新增 / 优化 / 修复 / 说明
- ...
```

建议按「新增 / 优化 / 修复 / 说明」分类填写，保持与历史条目风格一致。

### 4. `MoviePilot-Plugins/plugins.v2/larkmessager/__init__.py`

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
| `package.v2.json` | `version` → `0.8.0`；`description` 补海报说明；`history` 加 `v0.8.0` |
| `README.md` | `**版本**: 0.8.0` |
| `CHANGELOG.md` | 顶部加 `## v0.8.0 - 2026-07-09` 小节 |
| `__init__.py` | `plugin_version = "0.8.0"` |

## 提交前检查清单

- [ ] 四个文件版本号字符串完全一致（如均为 `0.8.0`）
- [ ] `package.v2.json` 仍为合法 JSON（可用 `python -m json.tool package.v2.json` 校验）
- [ ] `CHANGELOG.md` 新版本小节内容完整（新增 / 优化 / 修复 / 说明分类）
- [ ] 没有把 `tasks.md`、`agents_chat/`、`DESIGN.md`、`COMPARISON.md` 等开发文档误加入提交（按仓库规则这些不进 git）
