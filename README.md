# MoviePilot-Plugins

MoviePilot 第三方插件仓库

MoviePilot官方插件市场：https://github.com/jxxghp/MoviePilot-Plugins

## 插件列表

### OidcAuth - OIDC 认证

通过 OpenID Connect Provider 为 MoviePilot 提供插件化登录与账号绑定。

源自 [MoviePilot PR #5882](https://github.com/jxxghp/MoviePilot/pull/5882)，后经仓库维护者建议以插件形式实现。

- **版本**: 0.1.0
- **作者**: ui-beam-9, jxxghp
- **标签**: 认证, OIDC, SSO
- **图标**: Authelia_A.png

支持的 OIDC Provider 包括 Authelia、Keycloak、Casdoor 等兼容标准 OIDC 协议的服务。

#### 功能特性

- OIDC 授权码流程登录
- 已有账号绑定/解绑 OIDC 身份
- 新用户自动创建账号
- 登录票据认证桥接
- 可配置的自动创建用户角色

## 仓库结构

```text
MoviePilot-Plugins/
├── plugins.v2/oidcauth/    # OidcAuth V2 插件源码
├── icons/                   # 插件图标资源
├── package.v2.json          # V2 插件索引
├── package.json             # 默认插件索引
├── docs/                    # 开发与维护文档
└── .github/workflows/       # 发布工作流
```

## 开发文档

- [仓库指南](./docs/Repository_Guide.md)
- [V2 插件开发指南](./docs/V2_Plugin_Development.md)
- [常见问题索引](./docs/FAQ.md)
