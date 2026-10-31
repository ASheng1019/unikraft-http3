# HTTP/3 上游集成：归属、依赖与测试接收位置

2026-10-31 的本地设计决定。本文确定拟采用的职责和投稿位置；不代表维护者已接受。
本轮未发布 Discussion/issue/评论/PR。个人仓库继续作为可复现的集成入口。

## 部署支持与服务端口的划分

当前 `app-nghttpx/main.c` → `uk_nghttpx_run()` 的薄入口保持不变。协议栈、后端代理、
ACK 后响应内存回收仍复用上游。下列三处是部署能力的归属问题，不应以“QUIC 所需”
为由扩展 ngtcp2/nghttp3 的职责，也不应把服务私有头导入 app。

| 当前实现 | 归属决定 | 服务端口保留什么 | 投稿前的迁移要求 |
|---|---|---|---|
| `lib-nghttpx/Makefile.uk` 的三项 `--wrap`，`native_runtime.cc` 的 epoch/时钟实现 | 可信启动时间与 wrapper 启用由应用部署配置负责；通用 realtime/settime 由 core/POSIX time 负责 | 启动前检查服务所需 realtime 可用 | wrapper 必须显式启用，避免仅选择 HTTP/3 库就替整个镜像改时钟；可复用时间实现确定后再替换当前 adapter |
| `native_network.c` 的 netif MLD/link-local/SLAAC/DAD | netif 能力属于 lib-lwip，静态地址与选哪块网卡属于应用部署配置 | 请求使用已经配置好的 POSIX 网络 | 先补 netdev multicast 能力契约，再迁移通用初始化；静态地址必须能指定接口，保留 TCP/IP 线程内修改及 DAD 等待 |
| `native_runtime.cc` 的 token/UDP 控制口、drain、STATS | UDP 管理协议/token/STATS 属于应用部署支持；优雅退出属于 nghttpx 生命周期适配 | 调用上游 graceful-shutdown、销毁 watcher、限制单 worker 和 fatal VM exit | shutdown 与 STATS 分开可选；普通服务不应强制创建管理 UDP 口或携带 STATS FD 扫描；提供部署所需的 stop 触发方式 |

这些是后续迁移的明确接收边界，**本轮没有迁移运行时代码**，也未把“归属已定”写成
“能力已经变成可选”。现有镜像仍要求 `/native-boot.txt` 中的 epoch+token，默认创建管理口；
wrapper、IPv6 setup 和控制实现仍编译在 lib-nghttpx。这样保留已验证的部署契约，
先让维护者评估平台接口，再进行会影响所有镜像的跨仓库迁移。

### 时钟：为什么不能直接删除 wrapper

core `lib/posix-time/time.c` 的 `uk_sys_clock_gettime()` 将 realtime 交给
`ukplat_wall_clock()`；当前 `uk_sys_clock_settime()` 是 `UK_WARN_STUBBED()` 后返回0，
不能把“调用成功”当成已写入可信时间。现有 wrapper 用启动 epoch 加后续 monotonic 增量，
让 TLS 证书校验、ticket 和上游 `std::chrono::system_clock` 使用一致的时间。

`--wrap=clock_gettime/gettimeofday/time` 在最终链接生效，影响其它库对这三个符号的调用，
不构成平台 RTC、NTP 或完整 POSIX 时钟实现，也不保证直接 syscall 等路径受其覆盖。
归属不应是 OpenSSL、ngtcp2 或 nghttpx 的通用功能。与已有
[native clock RFC #1953](https://github.com/orgs/unikraft/discussions/1953) 协调，
但 adjtimex/timer 工作本身不等于已经提供首次可信启动时间。

迁移验收：有部署 provider 时 TLS/系统时间一致，monotonic/QUIC 计时不受 realtime 修改影响；
没有可信时间时明确失败；关闭 wrapper 时三个替代符号和链接选项确实消失；
同一镜像不得再叠加两个 realtime provider。保留 epoch 文件作为当前可运行 adapter，
不为仅一个部署凭空增加一套通用时钟框架。

### IPv6：通用能力与地址策略分开

当前 `native_network_init()` 通过 `tcpip_callback_with_block()` 修改 netif，并用 semaphore
等回调完成后才释放栈上的参数；静态 IPv6 等待 DAD，最多约6秒。这些同步和生命周期条件
必须保留，不能从应用线程直接改 lwIP 数据结构。

当前 `uknetdev.c` 设置 BROADCAST/ETHARP/LINK_UP，但没有设置 MLD6，服务临时补了该 flag。
这不能直接推广到所有 uknetdev：需确认驱动接收 multicast、MLD filter 的行为，并在
lib-lwip 的 netif 初始化路径声明能力；不能让 HTTP/3 端口擅自宣布所有网卡都支持。
link-local/SLAAC 可沿用 lwIP 的实现，应用只选启用方式和地址。现有“首个活动 Ethernet
接口”选择仅适用于本轮单网卡镜像，不升级为通用多网卡 Interface。

迁移验收：双栈、IPv4-only/IPv6-only 编译，真实 ND/DAD/MLD 运行、重复地址失败、
接口不存在/多接口选择和初始化超时。当前仅双栈单接口运行已覆盖；不要把编译矩阵称为运行验证。
修改 port 自有 netif glue 直接提交 lib-lwip；修改下载的 lwIP 源码才组织为适配补丁。

### shutdown 与 STATS：避免让观测成为必需的服务语义

上游 `worker_process_event_loop()` 的 graceful-shutdown/连接清理适配留在
`0003-service-lifecycle.patch`；触发 stop 的 token/UDP 协议属于部署控制。
超时 drain 的 VM shutdown 只符合单服务/单进程镜像契约。

STATS 当前将 context 转成 `shrpx::ConnectionHandler`，取得单 worker 计数、可选 allocator
统计，还在 event-loop 线程扫描0..4095 FD。因此不能原样移到 app 并导出上游私有 C++ 头。
迁移时由服务提供必要的只读统计快照；部署支持选择是否暴露它。FD 扫描属于显式诊断模式，
默认关闭，不将 unavailable 的 allocator 数值当成已观测峰值。

迁移验收：无管理口也能启动与提供 H3，未启用 STATS 时没有扫描路径；启用时认证失败无副作用；
正常 drain、持有连接到截止时间、重复 stop、watcher/FD 清理均验证。当前部署/故障回归覆盖
现有强制管理模式，**未覆盖尚未实现的关闭管理模式**。

## 官方依赖和版本接收

只读查询确认，core 和下列八个既有库的官方默认分支为 `staging`。正式 PR 应以投稿时的
目标分支为准；发行归档版本和 Git port 版本是两回事。当前不是“改 URL 就能全用官方版”：
LLVM/OpenSSL 更新和 socket 适配等尚需合并，固定 core 也仍带原作者的前置提交。

| 模块 | 拟接收仓库 | 当前前提/内容 |
|---|---|---|
| ARM64 core | [unikraft/unikraft](https://github.com/unikraft/unikraft) | 采用既有 #1875/#1876，保留作者与来源，不重复投稿 |
| musl | [unikraft/lib-musl](https://github.com/unikraft/lib-musl) | 固定 release 归档获取/元数据 |
| lwIP | [unikraft/lib-lwip](https://github.com/unikraft/lib-lwip) | 版本、独立 fixes、UDP 契约、TCP readiness、RX/checksum 分组；首轮止于 d6cf36b |
| C++ runtimes | [lib-libcxx](https://github.com/unikraft/lib-libcxx)、[lib-libcxxabi](https://github.com/unikraft/lib-libcxxabi)、[lib-libunwind](https://github.com/unikraft/lib-libunwind) | 沿用原 LLVM21 PR #38/#8/#13；本地元数据/配置修正作为后续 |
| TLS | [unikraft/lib-openssl](https://github.com/unikraft/lib-openssl) | 协同 #12，3.5.9 及能力检测/加速增量独立评审 |
| resolver/compression | [lib-c-ares](https://github.com/unikraft/lib-c-ares)、[lib-zlib](https://github.com/unikraft/lib-zlib) | 通用配置/构建和独立 contract 测试 |
| QUIC | 拟 `unikraft/lib-ngtcp2` | 新 port；首轮止于1b95dc9，无 PMTU 自定义策略及 hook |
| HTTP/3/QPACK | 拟 `unikraft/lib-nghttp3` | 新独立 port |
| HTTP/2/HPACK | 拟 `unikraft/lib-nghttp2` | 独立 C 库；不把 nghttpx 私有配置泄漏给它 |
| event loop | 拟 `unikraft/lib-libev` | 独立 port，POSIX epoll/timer |
| reverse proxy | 拟 `unikraft/lib-nghttpx` | 从同一 nghttp2 release 单独解包/打 service patches；无需依赖 lib-nghttp2 的私有源码树 |

上述五个拟建库和 `unikraft/app-nghttpx` 的公开 API 查询均返回404：只说明**目前没有可访问的
公开仓库**，不推断没有私有工作。不得现在把个人 URL 换成这些尚不存在的官方 URL，
或把官方组织下的仓库创建当成本轮已完成。独立应用是否需要官方 `app-nghttpx` 仓库也未定，
推荐先以 native catalog 示例接收，避免重复维护两个官方应用副本。

依赖顺序：core/LLVM/libc/TLS 前置 → lwIP/POSIX 契约及通用库 → ngtcp2/nghttp3/nghttp2/libev
→ lib-nghttpx → native 示例/集成 CI。基于来源 PR 做增量，保留 licenses、Signed-off-by、
原始作者；已有独立正确性回移继续单独存放。ACK deadline/PMTU 黑洞恢复不进入首轮依赖。

## Catalog 与 CI 的具体位置

推荐 native 示例进入 **`unikraft/catalog-core/nghttpx/`**。官方
[catalog-core README](https://github.com/unikraft/catalog-core#readme) 明确定位源码/Make/Kconfig
的 core/library 开发与测试；[nginx 示例](https://github.com/unikraft/catalog-core/tree/main/nginx)
已有薄应用+独立 port 的模式。面向最终用户的 [catalog](https://github.com/unikraft/catalog)
是后续分发集成，不先把源码原生服务伪装成已经支持的 ELF/bincompat 部署。

只读核对的提交：catalog-core main `1950f07ce85cdc2cd49f5eade50ff1d840ba33a6`、
test `d606aead7d8a6d39cc3d9f0720eff0526c1c28d8`，lib-lwip staging
`ec55ae17618feeb57c8c10109bcf5c42723e8e95`。依据：

- [port catalog-core-dispatch](https://github.com/unikraft/lib-lwip/blob/ec55ae17618feeb57c8c10109bcf5c42723e8e95/.github/workflows/catalog-core-dispatch.yaml)：
  staging PR → `lwip_open_pr`；组织 App token 由维护者配置。
- [catalog-core lib-lwip-tests](https://github.com/unikraft/catalog-core/blob/1950f07ce85cdc2cd49f5eade50ff1d840ba33a6/.github/workflows/lib-lwip-tests.yml)：
  接收 dispatch，checkout test 分支，调用 `.github/scripts/tests/run-tests.sh lwip clang`。
- [runner](https://github.com/unikraft/catalog-core/blob/1950f07ce85cdc2cd49f5eade50ff1d840ba33a6/.github/scripts/tests/run-tests.sh)：
  按 Makefile 中字面 `$(LIBS_BASE)/lwip` 等筛选应用，调用 `<app>/scripts/test/all.sh`。
  当前 app 的动态 LIBS 列表不会自动命中该字面筛选，不能宣称“放进去 CI 就会跑”。
- [nginx test 入口](https://github.com/unikraft/catalog-core/blob/d606aead7d8a6d39cc3d9f0720eff0526c1c28d8/nginx/scripts/test/all.sh)：
  实际路径是 `scripts/test/`，该分支不使用旧 README 所写的 `.scripts/test/`。

拟接收修改：

| 位置 | 具体内容 |
|---|---|
| 每个协议 port 的 `tests/upstream/` | ngtcp2/nghttp3 原生协议套件；单库构建，不依赖 nghttpx |
| c-ares/zlib 的 `tests/contract/` | 独立公共 Interface 合约；socket 修复测试属于 lwIP/其上游 |
| catalog-core main 的 `nghttpx/` + setup.sh | app 源码/配置、rootfs 约定、README/demo、正式依赖的获取；不导入 workspace/forks/tools |
| catalog-core test 分支 `nghttpx/scripts/{build,run,test}/` | 清洁 ARM64 build、TLS/H3→H1 smoke，调用同一个 demo；只选择实际支持的架构/平台 |
| catalog-core `.github/workflows/` 和 runner | ARM64/KVM 执行资源、HTTP3 client/依赖固定；增加显式库依赖识别和新 port dispatch；以 PR head 执行，不能误测 staging |
| catalog-core 集成测试扩展 | HTTP2/TLS/DNS origins、恢复/背压/双栈/wire、fault injectors；普通无策略矩阵与策略探索分开 |

现有 workflow 为 `ubuntu-latest`，未证明能提供本项目所需 ARM64/KVM。不得照搬 nginx 的
多平台 all.sh，将尚未支持的 x86/Xen/Firecracker 写为通过，也不在个人 fork 里虚设组织 token。
可以先接 build-only 检查；有明确 ARM64/KVM runner 后再将 runtime smoke 设为必须检查。
高频故障套件依赖实验宿主 libslirp，其已知边界未解决；不能静默预加载到官方 runner。
CI smoke 使用 stock QEMU usernet；扩展测试应显式固定并声明宿主依赖或选经过验证的替代拓扑。

## 本轮验收和后续顺序

先完成当前无策略版本的服务/故障注入回归，作为上述拆分之前的参考。新入口
`tests/build-base-service.py` 导出固定的 base 提交，拒绝 dirty/mismatched 模块，所有输出另存；
不切换、改写现有策略分支。`tests/run.py --profile base` 默认运行9项普通服务套件，
明确排除2项自定义黑洞/冷却/再探测策略用例，且拒绝用 base profile 点选它们。
两种故障注入另用各自镜像，不能把测试 wrapper 混入服务镜像。

普通 PMTUD/fresh-connection MTU、ECN/DF 和1200字节配置仍由 wire/defaults 覆盖；
排除的是既定自定义恢复行为，不是把基础 QUIC、IPv6 或全部 PMTU 验证跳过。
无策略版本不承诺已探测到大包后同连接黑洞恢复/再探测，也不沿用开发策略性能结果。
在不了解路径 MTU 的部署中，基础版可选择 `pmtud=no`、`max-udp-payload=1200`、`ecn=no`；
该保守模式有功能覆盖，尚无独立性能比较。

完成结果见 [validation](../validation/README.md)。上游顺序仍是先 Ideas 讨论确认归属、
仓库与 runner，再做跨库迁移及提交；本轮仅准备材料和验证，不执行对外发布。
