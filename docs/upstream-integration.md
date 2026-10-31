# HTTP/3 上游集成：归属、依赖与测试接收位置

2026-10-31 的本地设计决定。本文确定拟采用的职责和投稿位置；不代表维护者已接受。
本轮未发布 Discussion/issue/评论/PR。个人仓库继续作为可复现的集成入口。

## 已落实的运行时归属

入口为 `main.c` → app `app_nghttpx_run()` → `uk_nghttpx_run(options)`。
协议栈、TLS、后端代理、ACK 后内存回收仍复用上游；app 只配置部署支持。

| 实现位置 | 职责 | 可选性/Interface |
|---|---|---|
| app `clock.c`、`Makefile.deployment` | 从可信 epoch 锚定 realtime，提供三个全镜像 libc wrapper | APPNGHTTPX_BOOT_EPOCH 默认 n；关闭时不编译实现、不增加 --wrap；不属于 lib-nghttpx |
| app `deployment.c` | 解析部署文件、选择网络接口、配置 QUIC options 与生命周期 hooks | 未选择功能的配置键明确拒绝；epoch 与 token 分别按需读取 |
| app `control.c` | token/UDP 管理、drain 截止、可选统计及 FD 诊断 | CONTROL/SHUTDOWN/STATS/FD_STATS 分别选择；SHUTDOWN/STATS 依赖 CONTROL，FD_STATS 依赖 STATS；均默认 n |
| lwIP `ipv6.c`、`include/uk/lwip-ipv6.h` | 命名 netif 的 MLD/link-local/SLAAC/static 设置、TCP/IP 线程同步、DAD | LWIP_IPV6_SETUP 默认 n，依赖 threaded IPv6；地址、接口和 multicast 接收约定由调用者提供 |
| nghttpx `native_runtime.cc`、`entry.cc`、patch0003 | 服务配置校验、realtime/C++ clock 一致性检查、worker 生命周期、graceful shutdown 和只读 worker 快照 | options 可为 NULL；无 hooks 时不创建管理 socket、不读部署文件；只暴露公开 C types 和 opaque handle |

app 的 defconfig/Kraftfile **显式**开启 epoch、CONTROL、SHUTDOWN、STATS、IPv6，保持演示可运行；
这不是这些功能的 Kconfig 默认值。FD 扫描仍默认关闭。协议端口不会替应用选择上述功能。
原 service `native_network.c` 和私有网络头已删除，源码补丁0003只调用生命周期 hook，
不包含应用 UDP 管理协议。直接维护的 glue 不再伪装成第三方源码补丁。

### 时钟：显式 provider，保留安全失败

core `uk_sys_clock_settime()` 仍是 stub，ARM64 generic timer 的 epoch offset 为0。
未选择 app wrapper 时必须由其它 provider 提供有效 realtime；否则服务启动失败，
不能因为 clock_settime 返回0就认为时间已校准。服务同时检查 C realtime 与 C++ system_clock。
wrapper 只重锚 REALTIME/REALTIME_COARSE，MONOTONIC/QUIC timer 路径保持原时钟。

`/native-epoch.txt` 只含秒级 Unix epoch，独立于 `/native-control.token`。
旧 `/native-boot.txt` 合并契约已经移除，不能用旧 initrd 运行新版 app。
`--wrap=clock_gettime/gettimeofday/time` 由 app 选择，影响整镜像对这些符号的调用；
它不是 RTC、NTP 或完整 POSIX clock discipline，也不覆盖所有直接 syscall 路径。
继续与 [native clock RFC #1953](https://github.com/orgs/unikraft/discussions/1953) 协同。

关闭 wrapper 的成功路径用独立 `tests/platform-clock-app` 验证真实 POSIX 调用与 TLS 后端校验。
该镜像只在测试中替换 ukplat_wall_clock，不是新增的正式平台 RTC。
链接符号检查确认三个 app wrapper 全部不存在；无 provider 时另测启动失败。

### IPv6：显式接口、通用同步和 multicast 接收契约

`uk_lwip_ip6_configure(ifname, address, flags, timeout_ms)` 从应用线程调用，所有 netif 修改
通过 tcpip_callback_with_block 在 TCP/IP 线程执行；回调完成前不释放栈参数。
调用者必须指定接口，未找到、未 up 或不是 Ethernet 的接口返回 ENODEV，不选择首个活动设备。
单 virtio 的合格配置为 en1（lwIP loopback 占据 index0）。

uknetdev 当前没有完整 multicast/filter 能力位，本轮没有虚构自动检测结果。
`UK_LWIP_IP6_RX_MULTICAST` 是调用者对**指定接口**能接收 IPv6 multicast、无需硬件 filter
回调的显式约定；app 的 `ipv6-multicast-rx=yes` 提供该约定。缺失时不擅自设置 MLD6，
也不假定所有 uknetdev 都有能力。virtio 的实际收包通过双栈 ND/DAD 用例验证，其它设备仍须验证。

app 的 `ipv6-interface`、可选 `ipv6-address`/`ipv6-slaac`/`ipv6-dad-timeout-ms` 只表达部署选择。
通用 helper 等待 link-local/static DAD；重复地址返回 EADDRINUSE，超时返回 ETIMEDOUT，
配置不回滚，不能宣称失败后网络状态未变。SLAAC 初始化成功不代表已经取得全局地址。
真实 Linux peer 的重复地址、未知接口、缺失接口/能力约定、非法 multicast 地址和超时已纳入回归。
两版 lwIP 的 IPv4/IPv6/双栈/metadata 编译矩阵覆盖 helper 的 IPv6 构建；
单栈、多物理网卡运行及所有设备的 multicast 接收仍不作资格声明。

### shutdown/STATS：应用管理，服务只提供生命周期能力

`uk_nghttpx_options` 中 on_ready/on_close 必须成对；全部为 NULL 就没有应用管理端点。
callbacks 在 event-loop 线程执行，opaque control handle 只能在 ready/close 生命周期内使用，
不得跨线程或在关闭后保存。on_ready 失败须清理自身部分初始化。
`uk_nghttpx_shutdown(handle)` 幂等地请求上游 graceful shutdown，
`uk_nghttpx_get_stats(handle, snapshot)` 只暴露只读连接数，不导出私有 C++ 对象。

CONTROL 控制端点/token；SHUTDOWN 与 STATS 可以分别关闭，支持仅 shutdown、仅 STATS
及全部关闭。端点至少要有一种命令。无 CONTROL 时不编译管理实现、不要求 token，
由宿主 supervisor 结束 VM；测试中的宿主 teardown 不记作 guest graceful shutdown。
仅 STATS 时省略 drain-seconds，发 stop 不会退出。正常 shutdown 仍保留有界 drain 和 watcher/FD 清理。

FD_STATS 是独立诊断开关：未开时不存在4096项 fcntl 扫描，JSON 返回 fds=-1/scan_limit=0；
开启后才执行扫描。allocator 未提供统计时保留 unavailable=-1，不将其当成实测峰值。
链接/object 符号检查与实际认证/请求/退出测试一起验证，避免仅凭 UDP 无响应宣称代码被移除。

## 官方依赖和版本接收

只读查询确认，core 和下列八个既有库的官方默认分支为 `staging`。正式 PR 应以投稿时的
目标分支为准；发行归档版本和 Git port 版本是两回事。当前不是“改 URL 就能全用官方版”：
LLVM/OpenSSL 更新和 socket 适配等尚需合并，固定 core 也仍带原作者的前置提交。

| 模块 | 拟接收仓库 | 当前前提/内容 |
|---|---|---|
| ARM64 core | [unikraft/unikraft](https://github.com/unikraft/unikraft) | 采用既有 #1875/#1876，保留作者与来源，不重复投稿 |
| musl | [unikraft/lib-musl](https://github.com/unikraft/lib-musl) | 固定 release 归档获取/元数据 |
| lwIP | [unikraft/lib-lwip](https://github.com/unikraft/lib-lwip) | 版本、独立 fixes、UDP 契约、TCP readiness、RX/checksum 分组；首轮止于1a4d874（新增独立 IPv6 helper 提交） |
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

拆分前的无策略验证作为参考，拆分后的配置矩阵及服务回归另记于 validation。入口
`tests/build-base-service.py` 导出固定的 base 提交，拒绝 dirty/mismatched 模块，所有输出另存；
不切换、改写现有策略分支。`tests/run.py --profile base` 默认运行9项普通服务套件，
明确排除2项自定义黑洞/冷却/再探测策略用例，且拒绝用 base profile 点选它们。
两种故障注入另用各自镜像，不能把测试 wrapper 混入服务镜像。新增 unmanaged、shutdown-only、
stats-only、fd-stats、platform-clock 构建 profile，runtime-options 套件集中验证关闭功能后的行为。

普通 PMTUD/fresh-connection MTU、ECN/DF 和1200字节配置仍由 wire/defaults 覆盖；
排除的是既定自定义恢复行为，不是把基础 QUIC、IPv6 或全部 PMTU 验证跳过。
无策略版本不承诺已探测到大包后同连接黑洞恢复/再探测，也不沿用开发策略性能结果。
在不了解路径 MTU 的部署中，基础版可选择 `pmtud=no`、`max-udp-payload=1200`、`ecn=no`；
该保守模式有功能覆盖，尚无独立性能比较。

完成结果见 [validation](../validation/README.md)。上游顺序仍是先 Ideas 讨论确认归属、
仓库与 runner，再按维护者意见调整已经准备好的跨库 Interface 并提交；本轮不执行对外发布。
