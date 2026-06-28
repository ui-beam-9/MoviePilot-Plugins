# MoviePilot-Plugins

MoviePilot 第三方插件仓库

MoviePilot官方插件市场：https://github.com/jxxghp/MoviePilot-Plugins

## 插件列表

### OidcAuth - OIDC 认证

通过 OpenID Connect Provider 为 MoviePilot 提供插件化登录与账号绑定。

- **版本**: 0.3.4
- **作者**: ui-beam-9, jxxghp
- **标签**: 认证, OIDC, SSO
- **图标**: Oidcauth_A.png

支持的 OIDC Provider 包括 Authelia、Keycloak、Casdoor 等兼容标准 OIDC 协议的服务。

[了解更多](./plugins.v2/oidcauth/README.md)

---

### LarkMessager - Lark 应用消息通知

基于 [Lark 开放平台](https://open.larksuite.com/)（国际版飞书）自建应用的消息通知与交互插件，为 MoviePilot 提供完整的 Lark 消息通道。

- **版本**: 0.5.0
- **作者**: ui-beam-9
- **标签**: 通知, Lark, 交互
- **图标**: FeiShu_A.png

[了解更多](./plugins.v2/larkmessager/README.md)

---

## 仓库结构

```text
MoviePilot-Plugins/
├── plugins.v2/          # V2 插件源码（每个插件一个子目录，内含 __init__.py、前端源码等）
├── icons/               # 插件图标资源（供 package.v2.json 引用）
├── package.v2.json      # V2 插件索引（MoviePilot 读取此文件获取插件列表）
├── package.json         # 默认插件索引（V1 插件，当前未使用）
├── docs/                # 开发与维护文档（仓库指南、V2 开发规范、FAQ 等）
└── .github/             # GitHub Actions 工作流（自动发布、CI 等）
```

## 开发文档导航

- [仓库指南](./docs/Repository_Guide.md)
- [V2 插件开发指南](./docs/V2_Plugin_Development.md)
- [常见问题索引](./docs/FAQ.md)
- [MoviePilot 前端模块联邦开发指南](https://github.com/jxxghp/MoviePilot-Frontend/blob/v2/docs/module-federation-guide.md)

## License

本项目采用 [GNU General Public License v3.0](./LICENSE) 开源协议。
