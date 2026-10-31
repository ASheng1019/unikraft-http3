# HTTP/3 上游投稿计划与文本草稿

核对日期：2026-10-30。本文只在个人工作区维护；没有据此向上游创建 Discussion、issue、PR、评论或发送消息。
个人 GitHub 的 20 个仓库当前分支已逐一 push 并核对远端提交号。
已发布 PR 的正文继续以 GitHub 为准，不复制成另一套投稿快照。

## 1. 建议的投稿方式

先开 **一个 Unikraft HTTP/3 Ideas Discussion**，用现有可运行实现讨论接收方式：
新 library/service port 仓库、与已有依赖升级的协作、native 应用和集成测试的承载位置。
它不是请求维护者先批准每个小修复，也不要求实现全部合并到 core。

普通、独立且尚无重复工作的正确性修复可以直接提 PR；不为同一个小修复额外开一个 issue。
已有 PR 的工作接续原线程，不另开竞争 PR。PMTU 恢复、TCP ACK 时序、批量策略等行为设计
应先讨论，再提交单独实现，不能隐含在“移植库”中。

刚核对的上游 [project_backlog.yml](https://github.com/unikraft/unikraft/blob/staging/.github/ISSUE_TEMPLATE/project_backlog.yml)
明确将尚未讨论的新功能引导到 Discussions 的 Ideas 分类，backlog issue 用于已与核心团队讨论过的明确工作；
[config.yml](https://github.com/unikraft/unikraft/blob/staging/.github/ISSUE_TEMPLATE/config.yml) 关闭自由格式 issue。
因此修正此前“先开协调 issue”的建议：先 Discussion，接收方式明确后再按维护者建议创建 backlog/跟踪 issue。
这不要求普通独立修复也先开 issue。
Unikraft 官方要求一个 PR 聚焦一个主题，提交保留署名和 Signed-off-by，补充相关测试，
在投稿前运行 checkpatch，并在 Related Work 写清依赖。

依据：[贡献规则](https://unikraft.org/docs/contributing/unikraft)、
[评审过程](https://unikraft.org/docs/contributing/review-process)、
[应用 catalog 指南](https://unikraft.org/docs/contributing/adding-to-the-app-catalog)。
后者主要针对 binary compatibility；本项目是源码构建的 native 应用，不能直接照搬该部署模型。

## 2. 投稿对象、重复工作与处理方式

所有状态为本次查询时的公开状态；正式发布前要再次核对主线和讨论。

| 本地内容 | 上游对象 | 建议动作与前提 |
|---|---|---|
| core ARM64 FPSIMD/Clang | [unikraft/unikraft #1875](https://github.com/unikraft/unikraft/pull/1875)、关联 #1873 | 已保留原作者及来源采用原 PR，替换自写方案；干净构建和完整 11 项常规 HTTP/3 回归通过。不新开竞争 PR |
| core ARM64 枚举转换 | [unikraft/unikraft #1876](https://github.com/unikraft/unikraft/pull/1876)、关联 #1874 | 已采用原 PR 的完整修改；native 验证通过，Xen hunk 保留但未运行验证。不再投稿同一修复 |
| libc++ 21.1.8 | [unikraft/lib-libcxx #38](https://github.com/unikraft/lib-libcxx/pull/38) | 原升级作者 CristianAndrei1423；协作补上消费者配置隔离、包含顺序、getentropy 和归档元数据。后续新 PR 只保留我们的增量 |
| libc++abi 21.1.8 | [unikraft/lib-libcxxabi #8](https://github.com/unikraft/lib-libcxxabi/pull/8) | 现有升级 PR；我们的增量主要是 hash/版本元数据，优先并入原作者工作，不另开很小的竞争 PR |
| libunwind 21.1.8 | [unikraft/lib-libunwind #13](https://github.com/unikraft/lib-libunwind/pull/13) | 同上 |
| OpenSSL 3.5.x | [unikraft/lib-openssl #12](https://github.com/unikraft/lib-openssl/pull/12) | 现有 3.5.7 升级 PR；先协调版本/构建清单，ARM64 生成规则与能力分派作为独立增量；不得重新署名整个升级 |
| lwIP 版本及 socket 集成 | [unikraft/lib-lwip](https://github.com/unikraft/lib-lwip) | 已整理为版本/回移、UDP socket、TCP readiness、RX 交接/校验四个投稿单元；ACK deadline 单独留在最后一个策略提交，不随首轮 PR |
| c-ares 1.34.9 | [unikraft/lib-c-ares](https://github.com/unikraft/lib-c-ares) | 已恢复通用 resolver 描述和元数据，显式声明 musl/socket/POSIX 能力；不恢复失效 newlib 或强制 IPv6。独立 API/线程和真实 DNS 验证通过 |
| zlib 1.3.2 | [unikraft/lib-zlib](https://github.com/unikraft/lib-zlib) | 已补全 Library.uk，修正 README；HAVE_LIBC + 可选 gzip 文件 API，不强制 VFS/挂载。内存/流式 gzip/文件 API 独立验证通过 |
| musl 1.2.3 下载 hash | [unikraft/lib-musl](https://github.com/unikraft/lib-musl) | 不是新版本移植。可随该 port 的维护工作提交；无需为 hash 单独开协调 issue。当前新增 URL 被后文同名赋值覆盖，应先去除冗余 |
| ngtcp2 port | 候选 `unikraft/lib-ngtcp2` | 官方仓库尚不存在，先通过 Ideas Discussion 确认。基础分支 dev/ngtcp2-base-port 已移除 PMTU 策略及 patch hook，266 项 transport 目标测试通过；策略只在独立后续提交 |
| nghttp3 port | 候选 `unikraft/lib-nghttp3` | 同上；基础库不修改上游协议实现，独立验证 |
| nghttp2 C-library port | 候选 `unikraft/lib-nghttp2` | 同上；只包含 C 库及私有符号隔离，不混入 nghttpx 服务适配 |
| libev port | 候选 `unikraft/lib-libev`，名称待确认 | 同上；poll/epoll 及计时器能力如实声明 |
| nghttpx service port | 候选 `unikraft/lib-nghttpx`，或维护者指定的组织方式 | 协调后投；依赖前述库和 socket 能力。生命周期、数据报适配与通用正确性修复分别保留 |
| 薄应用、部署和跨库回归 | 优先与 [unikraft/catalog-core](https://github.com/unikraft/catalog-core) 协调 native 示例；必要时 [unikraft/catalog](https://github.com/unikraft/catalog) | 两个仓库均未归档；位置不能视为已获认可。先确定 native 构建入口及 CI 承载方式；不上传整个工作区或 QA 二进制 |
| nghttpx Retry | [nghttp2/nghttp2 #2933](https://github.com/nghttp2/nghttp2/pull/2933) | 已 open；继续原 PR，不新增 issue/PR |
| nghttpx 截断输入 | [nghttp2/nghttp2](https://github.com/nghttp2/nghttp2) | 本地/个人分支 `dev/drop-truncated-quic-input`；尚无 PR。可直接投稿，先核对无重复、重新验证 |
| lwIP 指针宽度、回环回调、MQTT、recvmsg | [lwip-tcpip/lwip #112](https://github.com/lwip-tcpip/lwip/pull/112)、[#113](https://github.com/lwip-tcpip/lwip/pull/113)、[#114](https://github.com/lwip-tcpip/lwip/pull/114)、[#115](https://github.com/lwip-tcpip/lwip/pull/115) | 均 open；继续原 PR，不重复开 issue。组合验证分支不是第五个投稿 |
| ngtcp2 PMTU 黑洞恢复 | [ngtcp2/ngtcp2](https://github.com/ngtcp2/ngtcp2) | 暂缓；以后先讨论策略和不变量，再提交实现。不要通过 Unikraft 基础 port 默认夹带 |
| libslirp TIME_WAIT | [GitLab slirp/libslirp](https://gitlab.freedesktop.org/slirp/libslirp) | 暂缓；个人 GitHub 是镜像，正式渠道是 GitLab issue/MR（或项目认可的邮件）。先修补已知反例，不把当前分支作为完成的修复投稿 |
| 总工作区、工具包、历史性能原始记录 | 个人 [unikraft-http3](https://github.com/ASheng1019/unikraft-http3) | 保留为复现和开发入口；不作为 Unikraft core 的一个大 PR |

公开关键词检索未发现专门的 ngtcp2/nghttp3/nghttpx 投稿，但这不能证明无人进行未公开工作，
也不能代替 roadmap/维护者确认。不要在 Discussion/issue 中写“这个领域没有 owner”。
仓库中部分 MAINTAINERS.md 仍有明显旧模板信息；协作以具体已有 PR 和维护者回应为依据。

## 3. 推荐顺序与投稿前的实际缺口

1. 保持已经公开的五个正确性 PR；待用户授权后再处理评论或新更新。
2. 先发布下面的 HTTP/3 Ideas Discussion，列出现有可运行代码与明确问题。
3. 在 #1875/#1876、LLVM 三个 PR 和 OpenSSL #12 提供最小增量/验证反馈，尊重原作者。
   这些评论也必须等用户授权后才能发送；目前只保存草稿。
4. nghttpx 截断输入可并行作为独立通用正确性 PR；与 Unikraft 新 port 审批无必然先后关系。
5. 优先推进独立 nghttp3、ngtcp2 基础 port、libev/nghttp2，以及各依赖 port 的通用维护。
   ngtcp2 首版基础库不依赖 nghttpx；TLS helper 等待兼容的 OpenSSL 增量。
6. 分批推进 lwIP socket/RX 能力；首轮投稿止于 dev/lwip-native-integration，不包含 ACK deadline。
7. 依赖和承载方式明确后，提交 nghttpx 服务、native 应用和适合上游 CI 的集成子集。
8. PMTU 恢复和 ACK deadline 等策略另开讨论；libslirp 候选继续留在个人实验分支。

### 3.1 实际投稿优先级与问题跟踪

下面是推进顺序，不要求每行全部合并后才准备下一行；评审可并行，合并遵守真实依赖。

| 顺序 | 对象 | 实际操作 |
|---|---|---|
| 1 | unikraft/unikraft Discussions / Ideas | 一个 HTTP/3 总体提案，附固定个人仓库、用途、范围与结果；请求确认新 port 仓库、服务/应用边界及已有工作 |
| 2 | 已有 core #1875/#1876、LLVM 三个 PR、OpenSSL #12 | 在原线程提供验证/协调最小增量；不另开重复 issue/升级 PR |
| 3 | unikraft/lib-zlib、unikraft/lib-c-ares、unikraft/lib-lwip | 通用 ports 各一个聚焦 PR；lwIP 先 A（版本/回移）。三者可并行，不等待整套 HTTP/3 接收 |
| 4 | 讨论后建立的新 port 仓库 | nghttp3、ngtcp2 transport-only 优先；nghttp2 C 库、libev 可并行；初始仓库接收方式由维护者确认 |
| 5 | unikraft/lib-openssl、lib-libcxx 及配套 runtime；lib-lwip | 接续原升级系列提交必要增量；lwIP 按 B→C→D 的整理序列推进。OpenSSL helper 随兼容 TLS 依赖就绪后启用/验证 |
| 6 | 维护者确认的 nghttpx service port 仓库 | 提交服务适配，链接全部前置 PR；投稿前补首轮无 PMTU/ACK 策略应用组合的对应回归，不能直接引用开发策略组合的全部成绩 |
| 7 | 维护者确认的 native 应用/catalog 位置 | 优先讨论 catalog-core；提交薄应用、部署说明与适合 CI 的集成子集 |

截至本次查询，五个候选官方新 port 名称均返回公开 API 404；不要向不存在的仓库准备可直接创建的 PR。
协调后只需一个明确的 HTTP/3 跟踪 issue，串联新 ports 与服务/应用；小修复、每个依赖升级和每个新 port
不分别制造同内容 issue。若维护者需要多个 backlog 项，再按其接受的拆分方式创建。
nghttp2 截断输入尚无 PR，可在其原仓库独立投稿；Retry 和四项 lwIP 修复继续已有 PR，不依赖该 Discussion。
PMTU、ACK deadline 及 libslirp 实验本轮不新建策略 issue 或 PR，保留独立提交待以后讨论。

个人仓库发布完成，**不等于当前所有开发分支已经可直接创建上游 PR**。具体需要：

- 已建立无 PMTU 补丁的 ngtcp2 基础投稿分支，独立目标套件为 266/266。
  开发组合的 297 项包含策略新增测试，两者分开记录，不能混用。
- libc++/OpenSSL 投稿基点应为原贡献者 PR 或合并后的主线，只展示我们的后续差异。
  libc++ 需要把消费者配置修复、随机源适配和元数据整理为有意义的提交。
- c-ares/zlib 已清除服务专用描述并补齐元数据与独立契约测试。c-ares 保留已验证的 musl ABI 限制，
  明确替换旧 newlib/强制 IPv6 配置；zlib 保留 HAVE_LIBC 接口边界，将 gz* 文件 API 作为依赖 HAVE_VFS 的选项。
  不承诺未测试 libc；原作者历史及上游许可证保留。正式投稿需说明配置迁移。
- lwIP 已从固定上游基线重建为可评审提交序列，四项独立上游回移仍逐项保留来源。
  无 ACK 策略的投稿终点通过独立 socket 验证；各单元与前一单元的关系见第 8.1 节。
  现有开发组合仅 README 改变，源码保持等价；不把整个开发策略分支提交上游。
- OpenSSL 需要评审生成清单维护、现有 core hwcap 接口是否可复用，以及其他架构的构建回归。
  当前 ARM64 检测/降级测试不等于已经验证全部支持架构。
- nghttpx 的全镜像 clock wrappers、IPv6 netif 初始化位置、部署控制接口和单 worker 限制需明确给维护者。
  C 源禁用 NEON intrinsics 是缺少 freestanding arm_neon.h 的构建 workaround，不能宣传为优化。
- 正式投稿前运行目标仓库要求的 checkpatch/CI，并核对新主线；本文不将未运行的检查标为完成。
  新官方仓库未建立前，不能向不存在的仓库创建 PR。

上面标为已完成的整理已经落实到独立分支；其余仍是投稿前的检查项。固定运行版本继续显式包含
已测量的策略提交，首轮投稿分支排除它们；两种组合分开构建、验证和记录。

## 4. 首个 Ideas Discussion：英文草稿（本地，未发布）

目标：[Unikraft Discussions](https://github.com/unikraft/unikraft/discussions/new)，分类 Ideas。
写法参考了 [#1945](https://github.com/orgs/unikraft/discussions/1945) 的用例→实现/环境→讨论问题，
以及 [#1837](https://github.com/orgs/unikraft/discussions/1837) 的简短设计要点；不套企业联络/内部 MR 模板。

当前 app README/demo 由工作区 gitlink 固定，个人仓库提供复现入口。
Discussion 仍为本地草稿；本轮不发布，也不向上游提交 PR。
讨论后再按维护者建议创建一个跟踪 issue，当前不新建 backlog issue。

标题：**Native HTTP/3 support with ngtcp2, nghttp3 and nghttpx**

下面英文正文可以在个人仓库同步、链接核对完成后直接用于 Discussion：

```markdown
Hi all,

I've been working on running an HTTP/3 reverse proxy natively on Unikraft,
and I'd like to discuss how to bring it upstream.

The use case is a small VM that terminates QUIC/TLS and forwards requests to
existing HTTP/1.1 or HTTP/2 origins. That lets an existing service offer
HTTP/3 without adding QUIC to the origin itself. This is a source-built
Unikraft application, using nghttpx as the proxy.

The working code is here: [HTTP/3 workspace](https://github.com/ASheng1019/unikraft-http3).
The [app README](https://github.com/ASheng1019/app-nghttpx#readme) covers the pinned
dependencies, build and a local demo. The demo starts an ordinary HTTP/1.1
origin, boots Unikraft under QEMU/KVM and checks a certificate-verified
HTTP/3 request and the response body.

The design mostly follows the upstream libraries:

- ngtcp2 handles QUIC transport; nghttp3 handles HTTP/3 and QPACK.
- OpenSSL provides TLS/crypto, through ngtcp2's OpenSSL helper.
- nghttpx handles the frontend, origin connections and response buffering.
  Its existing flow control and ACK-driven buffer reclamation are retained.
- libev drives readiness/timers over the POSIX interfaces; lwIP provides
  the UDP/TCP sockets.

The app prepares optional clock/network/management support, then calls
`uk_nghttpx_run(options)`. The service port owns lifecycle hooks and opaque
worker snapshots; protocol libraries remain usable independently.
The ports use Config.uk/Makefile.uk; changes to downloaded upstream sources
are carried as patches, and Unikraft glue is maintained directly in the ports.

The current working profile is ARM64/QEMU KVM with one application worker.
The development composition passes clean builds and 11 HTTP/3 regression
suites, including HTTP/1.1 and HTTP/2 origins, TLS session resumption, backend
failure recovery, dual-stack networking and in-connection MTU changes.
Multiple workers, other platforms, 0-RTT, QUIC DATAGRAM and WebTransport are
follow-up work. These are functional results, not a new Linux performance
comparison or a production qualification.

I'd suggest contributing this in smaller pieces: the independent library
ports and socket support, then nghttpx and a native example. There is also
experimental PMTU black-hole recovery and TCP ACK-deadline work in the
development composition. Those are separate commits and would be excluded
from the initial port PRs; the policy-free ngtcp2 and lwIP branches have their
own protocol/socket tests. The policy-free service also builds cleanly and
passes all nine applicable ordinary service suites, separate EAGAIN/truncation
fault images, and the local certificate-verified demo. The two custom PMTU
recovery suites are excluded from that profile; their results above belong to
the development composition.

This builds on existing ARM64 fixes and the LLVM/OpenSSL port updates. I'd
coordinate follow-ups with their authors rather than duplicate those changes.
Generic nghttp2/lwIP correctness fixes are being handled separately too.

There are a few platform details I'd like to agree on before submitting the
service port. The current image includes a trusted boot epoch, lwIP-specific
IPv6 setup and a small authenticated shutdown/STATS endpoint. I'd keep time,
address and management choices in deployment support, move general netif
initialization into the lwIP port, and retain graceful-shutdown hooks in nghttpx.
The runtime code now follows that split: deployment choices are explicit
app options, shutdown and STATS can be selected independently, FD scans default
off, and the lwIP helper takes an explicitly named interface and multicast
receive contract. The proposed interfaces still need maintainer review.

Does this seem like a useful direction? In particular, is there existing work
we should coordinate with, does this split between the libraries and the app
make sense, and where would you prefer the new ports and native example/tests
to live? I can adapt the submission series to the preferred layout.
```

### 4.1 应用设计评估与投稿条件

结论：薄应用 + 独立 service/protocol ports 的方向合理，已有实现和可运行演示足以讨论；
尚不能将整个个人工作区原样作为“已满足所有主线要求”的投稿。
官方 [catalog-core/nginx](https://github.com/unikraft/catalog-core/tree/main/nginx)
同样将应用构建、rootfs 和运行步骤与独立 library port 组合；应用没有大量 C 代码不是缺陷。

- **保留的划分**：main.c 调用 app 部署入口，由它准备公开 options，再调用服务 C Interface；
  协议和代理实现复用上游，不移入 app；
  demo.py 只是主机演示工具，不进入 unikernel 镜像，不导入工作区 QA fixture。
- **已补齐的复现入口**：app README 说明独立依赖工作区、干净输出构建、TLS 验证、initrd、
  后端及结果检查；不依赖本机私有工具路径，也不把所有开发 fork 当作构建输入。
- **显式部署 Interface**：uk_nghttpx_run(options) 是一次性、阻塞入口，要求调用者先配置网络与 realtime。
  app 的 epoch wrapper、管理端点、shutdown、STATS 和 FD 扫描分别由 Kconfig 选择；
  lib-nghttpx 不再隐式处理部署文件或替整镜像链接 wrapper。
- **归属已在代码中落实**：时间 adapter/UDP 管理在 app，命名接口 IPv6 通用同步与 DAD 在 lwIP，
  graceful shutdown/统计快照保留在 nghttpx。关闭管理功能可不带 token 启动；
  保留上游 worker/buffer 生命周期。接口、multicast 约定及验证边界见
  [upstream-integration.md](upstream-integration.md)，正式上游接收仍待维护者确认。
- **正式接收位置已有具体建议**：八个既有官方 port 的 staging，五个拟建独立 port，
  catalog-core/nghttpx 原生示例及 test 分支集成入口。API/runner 的核对结果及尚需维护者配置的
  ARM64/KVM runner、新库 URL/dispatch 见上述集成文档。无策略完整适用回归单独记入 validation；
  不能沿用完整策略组合的11项结果。
- **当前范围已经有实际用途**：单 worker 的 HTTP/3→TCP origin 代理是完整请求路径；
  无需为了展示工作量在 app 再写一套协议/代理，或先扩展到所有平台与多 worker。

## 5. 现有 PR 的协作文本草稿

下面都是**尚未发送的评论**。保留可以给对方 cherry-pick 的小提交/分支，不能直接推其分支。

### 5.1 core #1875：优先复用原 PR 的验证反馈

```text
I compared this change with the local FPSIMD assembly workaround in our
ARM64 HTTP/3 integration. The function-level __isr attributes remain in
place even when the file-level |isr build variant is removed.

With our current Clang19, -O2 and CONFIG_FPSIMD=y settings, both variants
compile. After aligning diagnostic source line numbers, all five functions
have identical instructions and relocation targets.

I replaced the local workaround with your original fix, preserving your
authorship, sign-off and source commit reference. A clean ARM64 build and
all 11 ordinary-image HTTP/3 regression suites pass on QEMU KVM, including
HTTP/1.1 and HTTP/2 origin proxying, TLS session resumption, backend fault
recovery, dual-stack wire tests and repeated in-connection MTU changes.

This qualifies our pinned compiler/configuration and does not claim coverage
of every compiler, optimization setting or LTO configuration.
```

本轮用实际 ectx.c 编译参数比较三种情况：原版 ISR 构建失败，本地方案和 PR 方案均可编译。
本地汇编指令导致源码多四行，最初对象差异仅为诊断行号；用空行对齐后指令及重定位目标一致。
这证明当前编译配置下的代码生成等价，不是所有编译器、优化配置及 LTO 的普遍证明。
不应仅凭移除文件级 `|isr` 就断言现有 PR 丢失全部限制或不安全：函数级 `__isr` 仍在。
现已在同一固定 core 基线上采用原 PR，以 `cherry-pick -x -s` 保留来源和作者；
自写汇编 feature 指令已移除。空输出目录重建和完整 11 项常规 HTTP/3 回归通过，
来源提交及集成提交记录在 sources.lock.json，具体运行范围见 validation/README.md。

### 5.2 core #1876：完全重合的修复

```text
The native ARM64 hunk matches the int-to-enum conversion used in our local
HTTP/3 build. I have adopted your complete original change with its authorship,
sign-off and source commit reference preserved. A clean Clang19 ARM64 build
and all 11 ordinary-image HTTP/3 regression suites pass on QEMU KVM.

I have not exercised the Xen hunk. I track this PR as the upstream prerequisite
instead of opening a duplicate PR for the native change.
```

### 5.3 libc++ #38 与配套 libc++abi #8、libunwind #13

```text
I am using your LLVM 21.1.8 port series for an ARM64 nghttpx HTTP/3 build.
I have kept your upgrade commits and authorship in the integration branches.

There are a few follow-ups I would like to coordinate: keep
_LIBCPP_BUILDING_LIBRARY private to the runtime translation units, preserve
libc++ wrapper include ordering for normal consumers, and use getentropy for
random_device on the qualified Unikraft profile. I also recorded release
archive hashes and matching Library.uk entries for the three runtimes.

The current consumer check passes after the configuration fix and fails with
the original leaked build macro; the integrated HTTP/3 build/regressions pass.
I can provide the focused follow-up commits. Would you prefer to incorporate
these in your series or have separate dependent PRs after the version update?
```

#8/#13 不重复发送整篇；若后续授权，只在需要时附其自身的元数据小改动。
不要求原作者修改其 vendored LLVM-libc 代码，也不把自动评论当作已确认的问题。

### 5.4 OpenSSL #12

```text
I am using your OpenSSL 3.5.7 update as the basis for an ARM64 HTTP/3 build
and have retained its history and attribution.

My follow-ups update the integration to 3.5.9, derive ARM64 source lists from
the configured OpenSSL build graph, and adapt capability dispatch to
Unikraft. AES/PMULL implementations remain upstream OpenSSL assembly;
detection is conservative, the environment mask can only remove capabilities,
and the fallback does not use SIGILL probing.

The ARM64 HTTP/3 regressions, independent ngtcp2/OpenSSL lifecycle/token tests,
and generated-manifest consistency check pass. Other architectures still
need separate qualification for my follow-ups.

Could we coordinate the release/source-list part with your existing PR and
keep the ARM64 generation/dispatch adapter as a separately reviewable change?
```

## 6. 独立 nghttp2 截断输入 PR：完整英文草稿

目标：`nghttp2/nghttp2`，默认主线 `master`；分支 `dev/drop-truncated-quic-input`。
不用再开一个同内容 issue。Retry 与四个 lwIP 修复已有 PR，正文和后续评审继续在原处维护。

标题：**nghttpx: Drop truncated QUIC input before interpreting it**

```text
QUICListener::on_read() can receive a datagram with MSG_TRUNC or MSG_CTRUNC
and continue interpreting its payload or ancillary data. A truncated payload
is not a complete QUIC datagram; truncated control data can omit metadata
needed to interpret its destination or traffic class.

Clear msg_flags for each recvmsg call and discard flagged input before
address/control parsing and connection dispatch. Complete datagrams keep the
existing receive path.

Add a Linux HTTP/3 regression covering payload truncation, control truncation
and both flags. Removing either guard reproduces the corresponding failure;
restoring the implementation passes and completes an HTTP/3 request.

Validated locally on ARM64 with strict ASan/UBSan, the existing HTTP/3 suite
and the three C/C++ unit suites. The Retry branch on the same upstream base
also passes Autotools distcheck; distcheck was not separately rerun for this
truncation branch in the latest refresh.
```

发布前再查重复、检查署名，并按 nghttp2 CONTRIBUTION 保持上游 MIT 许可与原文件版权；
Git 作者按用户已确认的 `Sheng <hsdai22@m.fudan.edu.cn>` 保留。

## 7. 新 port 的 PR 文本草稿

以下仓库名是候选，需第 4 节的协调结果。正文对应最终投稿范围，不是把当前 main 原样投递。
新建官方 port 仓库、接收初始提交/PR 的方式由维护者确认。
每项提交前附目标仓库模板，并完成其 checkpatch/CI，不能复制一个“全部已勾选”的清单。

### 7.1 nghttp3

标题：**Introduce the nghttp3 HTTP/3 library port**

```text
Add nghttp3 1.18.0 as an independent Unikraft library using the pinned upstream
release archive. The port provides build rules and a private configuration
header; HTTP/3 framing and QPACK remain unmodified upstream code.

Applications supply stream I/O and callbacks. This library does not depend
on ngtcp2, nghttpx or a particular event loop. Upstream public headers are
exported without exporting the private configuration directory.

Validated with all 61 upstream tests on ARM64/QEMU KVM and through the
nghttpx HTTP/3 integration. Other architectures/libcs are not qualified by
these results. Upstream MIT notices and the port-glue license are retained.
```

### 7.2 ngtcp2 基础库与可选 TLS helper

标题：**Introduce the ngtcp2 QUIC transport port with an optional OpenSSL helper**

```text
Add build rules for ngtcp2 1.25.0 as an independent QUIC transport library.
Applications retain ownership of sockets, time and protocol callbacks.
Expose the upstream experimental OpenSSL helper as a separate optional library requiring
a compatible OpenSSL 3.5+ port; the transport-only library does not need TLS
or nghttpx.

The base-port branch contains no provisional PMTU black-hole recovery patch
or patch hook. That policy is retained as one separate follow-up commit and
requires independent upstream discussion.

The base transport passes all 266 upstream tests on ARM64/QEMU KVM. The
development policy composition has 297 tests and is recorded separately.
The optional OpenSSL helper has prior independent entropy/time, 32-lifecycle
and crypto/token validation in the development composition; that is not a
claim that the helper probe was rerun on this base-port branch.
```

### 7.3 nghttp2 C 库

标题：**Introduce the nghttp2 HTTP/2 C-library port**

```text
Build the nghttp2 1.70.0 C library from its pinned release archive and export
its public headers. Keep configuration private and follow the upstream
library source inventory.

Prefix its private sfparse symbols at compile time so whole-library linking
alongside nghttp3 does not introduce duplicate private parser definitions.
This does not change the public HTTP/2 API or its protocol implementation.

The ARM64 nghttpx integration exercises HTTP/2 origin proxying. This PR is
the C-library port only; service lifecycle, QUIC I/O and deployment belong
to the separate nghttpx contribution.
```

### 7.4 libev

标题：**Introduce the libev event-loop port**

```text
Build unmodified libev 4.33 with explicit Unikraft backend selection. Provide
an epoll option with poll fallback, using libc clock and readiness interfaces.
Disable Linux-specific facilities that the qualified runtime does not supply.

The ARM64 nghttpx integration exercises socket readiness and timers. No
application event-loop policy or QUIC-specific instrumentation is added to
libev. The original licensing choices are retained.
```

### 7.5 nghttpx service port

标题：**Introduce the nghttpx native HTTP/3 reverse-proxy service port**

```text
Provide a single-worker ARM64 nghttpx service through the public C entrypoint
uk_nghttpx_run(options). Reuse upstream QUIC/HTTP/3, TLS, backend proxying, buffering
and ACK-driven reclamation; maintain Unikraft startup/network glue in the
port and carry changes to downloaded upstream sources as separate patches.

Separate generic Retry/truncation backports from service lifecycle and QUIC
datagram-I/O adaptation. Send individual UDP datagrams without GSO/GRO and
preserve packet boundaries under backpressure. Keep IPv4 DF and address/
traffic-class metadata consistent with the lwIP socket adapter.

The qualified deployment uses a private initrd, trusted boot epoch, one
worker and HTTP/1.1 or HTTP/2 origins. Clock wrappers affect the whole image
and are an explicit integration contract. Multi-worker operation, 0-RTT,
QUIC DATAGRAM and WebTransport are outside the initial scope.

The development composition passes 11 HTTP/3 regression suites, including
real dual-stack Ethernet and repeated in-connection MTU changes. The final
submission must distinguish standard PMTUD from the separately proposed
black-hole recovery policy and revalidate its exact dependency combination.
```

### 7.6 Unikraft PR 的统一外层格式

上面的主题正文放进目标仓库模板的 Description of Changes；Related Work 填该项真实依赖，
包括原作者 PR、总体 Discussion 和讨论后创建的跟踪 issue，不写“无依赖”。投稿时检查项以最终分支的实际结果为准：

```markdown
### Description of Changes

<使用该项的精简主题正文>

### Related Work

<列出该项真实依赖或协调链接；不要复制所有无关 PR>

### PR Checklist

- [x] Read the contribution guidelines.
- [ ] Tested the final submission branch on relevant architectures/platforms.
- [ ] Ran checkpatch.uk on the final commit series.
- [ ] Updated relevant documentation.
```

这是一份待完成的草稿外壳，不声称最终分支已完成所有检查。nghttp2 继续使用其简短正确性说明，
不强塞 Unikraft 的模板。提交消息保留原因、机制与验证，使用已确认的 Sheng 署名和 Signed-off-by。

## 8. 现有 Unikraft port 的投稿文本与拆分

这些是整理后的提交主题及正文草稿；当前组合分支在第 3 节列出的阻塞项完成前不直接投稿。
同一个 PR 可以有多个有意义的提交，不必强行全部 squash 成一个提交，也不按文件拆大量 PR。

### 8.1 lib-lwip

目标：`unikraft/lib-lwip`；先由总体 Discussion 确认阶段边界。

**PR A 标题：Version the lwIP patch series and add a pinned 2.2.1 source option**

```text
Add an immutable lwIP 2.2.1 source choice with archive verification and
version-specific Unikraft adaptations. Preserve the existing source choices
and their configuration behavior. Keep generic upstream backports separate
from libc/platform adaptations, with source references and removal rules.

The selected 2.2.1 composition passes native sanitizer tests and the ARM64
socket/HTTP/3 integration. Configuration selection is covered separately;
those selection checks do not imply runtime qualification of every old source.
```

**PR B 标题：Support UDP packet metadata and consistent DF socket semantics**

```text
Provide bounded socket-address results and UDP source/destination and
traffic-class metadata needed for QUIC replies. Support IPv4 DF requests,
retain DF when UDP allocates a separate header pbuf, and return EMSGSIZE
consistently from sendmsg and sendto for interface-MTU violations.

Keep IP-family code conditional and validate metadata off/on for both pinned
sources in IPv4-only, IPv6-only and dual-stack builds. Runtime checks cover
actual IPv4 DF packets, dual-stack metadata and socket copy/error contracts.
This adapter does not emulate Linux's PMTU cache.
```

**PR C 标题：Refresh persistent TCP readiness after partial receives**

```text
Refresh the Unikraft socket readiness level after lwIP updates lastdata.
Retained TCP bytes must remain readable, and draining the last pbuf must clear
readability without waiting for another packet. Keep this correctness change
separate from ACK scheduling policy.
```

**PR D 标题：Defer status-callback RX work and verify wire checksums**

```text
Hand status-callback RX work to the configured dispatcher instead of queuing
packets recursively into tcpip_thread's own mailbox. Preserve poll-only mode.
Verify complete incoming packet checksums because this adapter does not
consume checksum-offload metadata. Partial-checksum/GSO input is unsupported.
```

**暂缓策略：Add an opt-in independent TCP ACK deadline**

仅保留在一个独立后续提交中，不进入 A–D 的任何 PR。默认关闭，开发应用继续选择 50ms；
以后讨论计时器所有权、取消与现有 TCP timers 的关系，再决定投稿。
ngtcp2 PMTU 策略同样保留为基础 port 之后的独立提交。

本地可复核的投稿单元如下；它们按依赖叠放，不能对上游默认分支直接使用整段累计 diff：

| 单元 | 比较范围（lib-lwip 内） | 内容 |
|---|---|---|
| A | ec55ae1..8935f6f | 补丁目录版本化、固定源码、2.2.1 ABI 兼容、四项独立正确性回移及 2.1 recvmsg 对齐 |
| B | 8935f6f..3c4e35d | 地址复制边界、UDP ancillary data、DF/EMSGSIZE，三个逻辑提交 |
| C | 3c4e35d..a34ae8c | 持久 TCP readiness，一个提交 |
| D | a34ae8c..d6cf36b | RX dispatcher、软件校验，各一个提交及配套说明 |
| 暂缓 | d6cf36b..b20ebaf | ACK deadline，一个独立策略提交，首轮排除 |

A 的固定源码终点另有 dev/lwip-pinned-releases；包含回移的 A 终点为
dev/lwip-release-backports。B、C 和 D 的终点分别为 dev/lwip-udp-socket-contracts、
dev/lwip-tcp-readiness、dev/lwip-native-integration。完整提交号记录在 sources.lock.json
及个人仓库；历史大提交仍可追溯，但不再作为投稿序列使用。

已在 Unikraft 原基线存在的 common/ TIME_WAIT 处理保持原样；不能把保留旧行为称为新引入的策略。
可复用的 lwIP 功能未来仍可与 lwIP 上游讨论，Unikraft 设备/事件接口留在 port。

### 8.2 lib-c-ares

标题：**Update c-ares to 1.34.9 and refresh the Unikraft build configuration**

```text
Refresh the source inventory and platform configuration for c-ares 1.34.9,
using a pinned verified archive. The intended contribution is a reusable DNS
resolver port; the nghttpx workload is one consumer rather than its API scope.

The current integration covers DNS resolution, dropped replies and NXDOMAIN.
Use a generic resolver configuration with explicit musl ABI, socket, time,
poll, pipe and entropy requirements. Do not restore the removed newlib path
or force IPv6. Standalone DNS parsing/truncation, channel configuration and
poll event-thread lifecycle contracts pass without nghttpx.
```

### 8.3 lib-zlib

标题：**Update zlib to 1.3.2 and refresh its build metadata**

```text
Build zlib 1.3.2 from a pinned verified archive and refresh the source/config
rules. Preserve the library's general-purpose interface and record complete
Library.uk metadata and the original licensing notices.

Require HAVE_LIBC for the memory APIs and offer gzip file I/O separately
when HAVE_VFS is available. Leave the filesystem and mounts to the application.
Standalone tests pass for memory compression/decompression, corrupted input,
CRC, gzip-format streaming and gzip-file round trips. The memory-only profile
also verifies that gz* file symbols are absent while compress2 remains.
```

### 8.4 lib-musl 与 runtime 元数据

不为每个 hash 开独立 issue。libc++abi/libunwind 元数据优先交给既有升级系列整合；
musl 在维护者希望单独接收时，才准备一个聚焦的维护 PR。

候选标题：**Verify the pinned musl release archive**

```text
Record the checksum for the existing musl 1.2.3 archive in the Unikraft fetch
rules. This does not upgrade musl or change its runtime behavior. Keep the
URL derived from LIBMUSL_VERSION rather than adding a second overwritten URL.
```

### 8.5 OpenSSL 增量 PR

接续 #12 后的候选标题：**Add reproducible ARM64 source generation and capability dispatch**

```text
Derive the ARM64 OpenSSL source inventory from its configured build graph and
use upstream generated assembly implementations. Adapt capability dispatch
to the qualified Unikraft runtime with conservative detection and a mask that
can only disable capabilities. Require preserved FPSIMD context.

The manifest check, independent ngtcp2/OpenSSL probe and HTTP/3 regressions
pass on ARM64. Complete the agreed non-ARM64 build checks before submission.
The existing OpenSSL version-update work remains attributed to its author;
this PR must show only the agreed follow-up delta.
```

## 9. 应用、集成回归和暂缓讨论的文本

### 9.1 native 应用/catalog

候选：`unikraft/catalog-core` 的 `nghttpx/`，由维护者确认后再建投稿分支。
标题：**Add a native nghttpx HTTP/3 reverse-proxy application**

```text
Add a thin application calling uk_nghttpx_run(options), a reproducible ARM64 source
build profile and deployment instructions. Protocol/service implementation
stays in the library ports. Configuration, certificates, keys and the trusted
boot/control data are supplied privately at deployment time.

The application has passed clean-build, HTTP/3 origin proxying, dual-stack
wire, failure-recovery and MTU-change regressions in the pinned workspace.
Adapt the final manifest to accepted dependency repositories and provide the
catalog's required packaging/run instructions before submitting this PR.
```

集成测试不另建一个“导入整个工作区”的 core PR。可放独立 protocol 单测在各 port，
将服务烟测/真实后端/双栈契约作为应用 CI 子集；完整 KVM/故障/历史性能工具留个人工作区，
等 CI 接收方式明确后再移植合适的部分。不要把测试凭据、工具二进制或未验证的性能结论投稿。

### 9.2 ngtcp2 PMTU（暂缓；未来先 issue）

标题：**Discuss PMTU black-hole recovery and bounded re-probing**

```text
I would like feedback on recovering an established QUIC connection when a
path's usable MTU decreases without reliable ICMP feedback. The prototype
tracks suspicious losses and ACK progress, falls back to a baseline packet
size, and delays re-probing to avoid repeated oversized probes.

The open design questions are loss versus black-hole discrimination, recovery
when there is no ACK progress, path-generation resets, cooldown/re-probe
ownership and interaction with congestion recovery. The prototype currently
uses 60-second cooldown and 600-second periodic search; these are provisional
parameters for discussion, not proposed universal defaults.

I can provide native tests and HTTP/3 MTU-decrease/recovery traces. The policy
is separate from the Unikraft base port and references Quinn's prior work with
its attribution and license retained.
```

### 9.3 libslirp TIME_WAIT（暂缓；当前不发 issue/MR）

不准备“修复已完成”的 PR 正文。以后若决定报告，最先讨论的对象应是最小复现和期望的 TCP
行为，先补旧序列号隔离、重开本地 ISN、异常 SYN 控制位及 IPv6 的断言和实现。
可用的未来问题标题：**TIME_WAIT reopening: sequence-space and control-flag handling**。
现有候选的四个审计反例尚未通过，不能用原始 fixture 通过来掩盖这些边界。

## 10. 本轮明确不执行的上游操作

本轮没有创建或更新上游 Discussion、issue、PR 或评论，也没有联系维护者；全部新文本仅为草稿。
既有 PR 状态查询和公开检索都是只读。个人 GitHub 同步不修改上游默认分支。
后续实际发布哪一个 Discussion/issue/PR/评论，等待用户另行授权；不会自动按本文批量发送。
