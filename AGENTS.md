# AGENTS.md — LarkMessager 插件维护规则

本文件为参与本插件（`plugins.v2/larkmessager`）维护与开发的 Agent / 协作者提供**硬性规则**。版本发布的详细操作步骤见 [docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md)。

## 版本号发布硬性规则

每次更新插件版本号（如 `0.7.0` → `0.8.0`）时，**必须同步修改以下 4 个文件**，保证版本号、描述、版本历史、更新日志完全一致。遗漏任一文件都会导致 MoviePilot 插件市场显示的版本与代码实际版本不一致。

1. `MoviePilot-Plugins/package.v2.json`
2. `MoviePilot-Plugins/README.md`
3. `MoviePilot-Plugins/plugins.v2/larkmessager/CHANGELOG.md`
4. `MoviePilot-Plugins/plugins.v2/larkmessager/__init__.py`

各文件具体改什么、怎么改，见 [docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md)。

## 提交前检查清单

- [ ] `package.v2.json`：`LarkMessager.version` + `description` + `history` 三处已更新
- [ ] `README.md`：LarkMessager 小节 `**版本**: X.Y.Z` 已更新
- [ ] `CHANGELOG.md`：已新增 `## vX.Y.Z - YYYY-MM-DD` 小节并填写变更
- [ ] `__init__.py`：顶部 `plugin_version = "X.Y.Z"` 已更新
- [ ] 四个文件的版本号字符串完全一致

## 版本号约定

- 采用语义化版本 `主.次.修订`
- 新增功能 / 可见能力变化 → 升 `次` 版本（如 `0.7.0` → `0.8.0`）
- 仅修复 bug、无能力变化 → 升 `修订` 版本（如 `0.8.0` → `0.8.1`）

## 相关文档

- 版本发布详细步骤与示例：[docs/RELEASE_GUIDE.md](./docs/RELEASE_GUIDE.md)
