# PocketGate

Self-service DNS gateway: **PocketBase 里加一条记录，DNS 自动同步；删掉记录，DNS 自动回收。**

PocketGate 是 [BunCNAME](https://github.com/shenwii/BunCNAME)（GPL-3.0，作者 @shenwii）的深度改造版：

- 新增 **Cloudflare** DNS 服务商适配器（API v4，Bearer Token）
- **PocketBase 自动触发**：`pb_hooks/dns_sync.pb.js` 监听 `domains` / `dns_records` 两个 collection，记录一变就把全量期望状态推给 `/sync`，另有每 5 分钟一次的 cron 兜底防漂移
- **A / AAAA 记录支持**：通过 `MANAGED_TYPES=CNAME,A` 配置（默认只管 CNAME）；AdGuard Home 侧 rewrite 自动按 answer 是 IP 还是域名分类为 A/AAAA/CNAME
- **/sync 接口鉴权**：设置 `SYNC_TOKEN` 后必须携带 `X-Sync-Token` 头（hmac 常量时间比较）
- **失败不再静默**：调和结果返回逐域摘要（created/updated/deleted/errors），任何失败都返回 HTTP 500 而非假 200

## 架构

```
PocketBase (domains / dns_records collections)
   │  记录变更（create/update/delete）→ pb_hooks 全量重建 payload
   ▼  POST /sync (+ X-Sync-Token)
PocketGate 同步服务 (FastAPI, Reconciler)
   │  全量调和：多的删、缺的建、变的改；只碰 MANAGED_TYPES 白名单内的类型
   ├─→ Cloudflare (公网 DNS)
   ├─→ Porkbun   (公网 DNS)
   └─→ AdGuard Home (内网 DNS rewrite)
```

双 Nginx LuaJIT 动态反代（网关层 + 内网层）在 Roadmap 中，见下文。

## 快速开始

```bash
cp .env.example .env   # 填入 CLOUDFLARE_API_TOKEN / SYNC_TOKEN / AdGuard 信息
docker compose up -d   # buncname + pocketbase + adguardhome
```

然后在 PocketBase（`http://127.0.0.1:8090/_/`）里建两个 collection：

- **domains**：`domain` (text, required)、`providers` (text，存 JSON 数组如 `["cloudflare","adguard_home"]`，兼容逗号分隔)
- **dns_records**：`domain` (relation → domains, required)、`host` (text, required)、`type` (text)、`content` (text, required)、`ttl` (number, min 60)

> 也可用仓库里的 `sql/domains.sql` / `sql/dns_records.sql` 作参考在任意数据库里维护期望状态，只要能组出同样结构的 JSON POST 到 `/sync`。

往 `dns_records` 插一条 `www → CNAME → target.io`，几秒内 DNS 上就会出现；删掉它，DNS 记录随之回收。

> 注意：`adguard/adguardhome` 与部分基础镜像在 Docker Hub 上，网络不通时需自配镜像加速；PocketBase（ghcr.io）与本项目镜像不受影响。

## 直接调用 HTTP 接口（不经 PocketBase）

```bash
curl -X POST http://localhost:8000/sync \
  -H "Content-Type: application/json" \
  -H "X-Sync-Token: $SYNC_TOKEN" \
  -d '[{"domain":"example.com","providers":["cloudflare"],
        "records":[{"host":"www","type":"CNAME","content":"target.io","ttl":600}]}]'
```

成功返回逐域摘要；任何 provider 侧失败返回 HTTP 500 并携带 `summary.errors`。

## 配置（环境变量）

| 变量 | 说明 |
|---|---|
| `SYNC_TOKEN` | /sync 共享密钥；不设则接口无鉴权（强烈建议设置） |
| `MANAGED_TYPES` | 受管记录类型白名单，默认 `CNAME`；如 `CNAME,A` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API Token（Zone:Read + DNS:Edit，建议按 zone 收窄） |
| `PORKBUN_API_KEY` / `PORKBUN_SECRET_KEY` | Porkbun（可选） |
| `ADGUARD_HOME_URL` / `_USERNAME` / `_PASSWORD` | AdGuard Home（可选） |
| `BUNSYNC_URL` / `BUNSYNC_TOKEN` | 设在 **PocketBase 进程**上，指向 /sync 地址与 SYNC_TOKEN |

Cloudflare 注意事项：记录一律以 DNS-only（proxied=false）创建；TTL 最小 60（低于会被钳到 60）；TTL=1（auto）不被使用。

## PocketBase hook 手工部署（不走 compose 时）

```bash
BUNSYNC_URL=http://127.0.0.1:8000/sync BUNSYNC_TOKEN=xxx \
  ./pocketbase serve --dir=/srv/pocketgate/pb_data --hooksDir=/srv/pocketgate/pb_hooks
```

> **坑（v0.23 实测）**：
> 1. hook 回调运行在池化 JS 运行时里，闭包和顶层函数/常量在回调内**不可见**（报 `ReferenceError`），且回调内抛错会把记录请求变成 400（记录实际已写入）。所以 `dns_sync.pb.js` 里每个回调都是完全自包含的，改动时不要提取公共函数。
> 2. collection 若没有 `created` 字段，`findRecordsByFilter` 不要用 `-created` 排序。
> 3. `pb_data` 默认按**二进制所在目录**解析而非 cwd——`superuser upsert` 与 `serve` 务必都显式传 `--dir`，否则超管会写进另一个库、认证永远失败（已踩）。
> 4. collections 建好之前，cron 兜底任务每 5 分钟报一条 `sql: no rows in result set` ERROR 日志，属正常噪音，建表后消失。

## 安全须知

- `/sync` 是破坏性全量调和：payload 里没出现的受管记录会被删除。先在测试域验证，并在生产启用 `SYNC_TOKEN`、只绑内网。
- `.env` 永不入库（已进 `.gitignore`）。

## Roadmap（下一阶段）

- 网关 Nginx + 内网 Nginx 双层 LuaJIT 动态反代（复用 `ghcr.io/shenwii/nginx` 镜像思路），实现"加服务 = 起容器 + PB 加记录"全自动
- PVE 验证环境部署联调（需 PVE API Token 或目标机 SSH）
- PocketBase collection schema 迁移脚本（pb_migrations）

## License

GPL-3.0（继承自 BunCNAME）。Derived from [shenwii/BunCNAME](https://github.com/shenwii/BunCNAME).
