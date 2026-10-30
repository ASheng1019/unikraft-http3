# 工作区维护与提交边界

## 目录各自负责什么

- `unikraft/`：Unikraft core 原始 Git 仓库，保留两项 ARM64 前置修改。
- `libs/`：各 external-library port；Config.uk、Makefile.uk、平台 glue 直接维护在各 port。
- `app-nghttpx/`：薄应用入口、Kraftfile、部署配置。
- `forks/`：nghttp2、lwIP、ngtcp2、libslirp 的独立 Git 开发仓库。用于维护通用修复和回应上游评审，不是构建输入。
- `core-patches/`：从当前 core 修改导出的两项前置补丁，供 setup-core.sh 的主线基线重建使用。
- `tests/`：HTTP/3、socket、PMTU 等集成测试；`tests/upstream/` 是独立上游修复的原生回归。
- `tools/`、`cache/`、`build/`：本地工具、下载归档和可再生成的构建/测试输出，不提交给 port 仓库。
- `validation/`：当前验证说明和唯一保留的 Linux VM 性能对照。

原 `upstream/` 中十份重复工作树已删除，四个主仓库移到 `forks/`；所有命名分支和未投稿提交仍在 Git 中。
原 `submissions/` 的 PR 文本、完整 diff、重复 format-patch、逐文件 SHA256 清单和重放校验器已删除。
后续直接以 Git 提交、GitHub PR 和实际回归为准，不再维护第二套投稿文件快照。
源码下载校验值仍保留在各 port 和 sources.lock.json 中，用来验证构建依赖。

## 通用修复及 Unikraft 对应关系

| 修复 | 上游位置 | Unikraft 侧 |
|---|---|---|
| nghttpx Retry 分类 | [nghttp2 #2933](https://github.com/nghttp2/nghttp2/pull/2933)，`dev/review-retry-state` | lib-nghttpx/patches/0001，生产逻辑与投稿一致 |
| nghttpx 截断输入 | `dev/drop-truncated-quic-input`；GitHub 拒绝创建 PR，仍待投稿 | lib-nghttpx/patches/0002，生产逻辑与该提交一致 |
| lwIP 单测指针宽度 | [lwIP #112](https://github.com/lwip-tcpip/lwip/pull/112)，`dev/detect-unit-test-pointer-width` | lib-lwip/patches/2.2.1/fixes/0001，仅测试配置 |
| lwIP 回环回调类型 | [lwIP #113](https://github.com/lwip-tcpip/lwip/pull/113)，`dev/fix-loopback-callback-type` | 同目录0002，生产修复及原生回归 |
| lwIP MQTT 长度上限 | [lwIP #114](https://github.com/lwip-tcpip/lwip/pull/114)，`dev/reject-overlong-mqtt-length` | 同目录0003，生产修复及原生回归 |
| lwIP recvmsg 复制长度 | [lwIP #115](https://github.com/lwip-tcpip/lwip/pull/115)，`dev/fix-recvmsg-truncation` | 同目录0004，生产修复及原生回归；pinned-2.1 的既有独立补丁也同步返回值表达式 |

四个 lwIP 分支各一个提交；`dev/lwip-correctness-validation` 仅组合它们供原生验证。
nghttp2 已发布的 Retry 分支保持原名，避免影响现存 PR；后续新分支按修复机制命名。
每个 port 修复补丁头部记录来源 PR/提交及回移基线。MQTT 在2.2.1上的回归只移入本 PR 新增测试，
没有顺便导入 master 上原有、但 release 尚无的 rx_overflow 测试。

目前集成继续固定 nghttp2/nghttpx1.70.0、lwIP2.2.1、ngtcp2 1.25.0、nghttp3 1.18.0、
OpenSSL3.5.9，以及成套 LLVM21.1.8 runtime。对齐的是修复实现和来源，不将发行版直接换成移动的 master。

## 补丁与直接代码的边界

修改下载的第三方源码放进所属 port 的 `patches/`；修改平台 glue、构建规则、配置和公开头直接写 port 代码。
通用正确性修复逐项独立，不与 Unikraft 适配、ACK 策略或其它修复合并。
lwIP2.2.1 的应用顺序是 `common/` → `fixes/` → `native/`；各目录内按文件名排序。
nghttpx 的0001/0002是独立通用修复；0003处理服务生命周期和配置边界，0004处理 QUIC 数据报 I/O、元数据和缓冲区限制。
ACK 后释放响应存储、HTTP 后端背压属于上游已有实现，不归为移植补丁。

上游合并后，先升级到**实际包含该修复**的固定 release/commit，再删除对应修复补丁并干净重建。
PR 合并不会改变仍在使用的旧发行版，不能在合并当天直接删除旧版所需的回移补丁。
如有上下文重叠，重基后续适配补丁；保留真正的平台改动并重新运行回归。

## 暂缓的工作

ngtcp2 的 PMTU 黑洞恢复是策略提案：有/无 ACK 恢复、回退后确认、60秒冷却和600秒再搜索，
保留在 `forks/ngtcp2` 的 `dev/pmtu-recovery` 及 lib-ngtcp2 的独立补丁中，暂不投稿。
Quinn 参考与许可证保留，策略阈值须经维护者讨论；设计见该仓库 doc/pmtud-recovery.rst。

libslirp 的 TIME_WAIT 候选也暂缓：本地 ISN 选择、旧重复报文隔离、窗口内异常 SYN 控制位和 IPv6
仍需补齐。代码保留在 `forks/libslirp`，已知反例入口是 tests/upstream/libslirp-audit.py。
宿主测试仍显式选择 tools/slirp/out 的4.9.5库，不更换系统库；它不是 guest lwIP 的一部分。

## 后续提交给哪些仓库

- `unikraft/` 的两项前置修复 → unikraft/unikraft，各自独立。
- 八个已有 port（musl、lwip、libcxx、libcxxabi、libunwind、openssl、c-ares、zlib）→ 各自 unikraft/lib-* 仓库。
- 新 port（ngtcp2、nghttp3、nghttp2、libev、nghttpx）→ 申请/确认对应 port 仓库后分别提交。
- 应用、部署及跨库测试 → 应用/catalog 或相应 CI；具体承载形式与维护者确认。
- 此工作区本身、forks、工具、归档及本机生成日志不整体提交给 Unikraft core。

LLVM/OpenSSL port 延续原贡献者工作，保留原历史、署名和许可证。

## 2026-10-30 发布布局审查

个人 GitHub 上的 `unikraft-http3` 只承载集成源码、测试和固定的 Git submodule 引用。
`unikraft/`、13 个 `libs/lib-*`、`app-nghttpx/` 及四个 `forks/` 各自独立；
原有项目 fork 官方仓库，新 port/应用单独创建。libslirp 上游在 GitLab，个人 GitHub
是保留历史的镜像，不冒充 GitHub fork。上游投稿仍按上面的贡献边界进行。

新增 port 补齐发布元数据、实际作者 BSD 许可及自己的忽略规则，第三方许可保持原样。
删除 tx-burst 的无效配置和无调用 getter；目前唯一生产 TX 模式是逐数据报发送。
修正 QUIC UDP 监听器的 IPv4 DF 设置、lwIP 独立 UDP 头部的 DF 传播，以及 sendto
的 EMSGSIZE 返回。两个固定 lwIP 版本的 ancillary 适配按 IP 家族加条件编译。
IPv6/IPv4 单栈只增加编译覆盖；运行验证范围仍是 ARM64 双栈服务。

本轮个人仓库上传不等于创建新上游 PR。ngtcp2 PMTU 和 libslirp TIME_WAIT 仍是策略/实验分支；
后者已知限制不作为已解决问题发布。已有 PR 分支重基后采用明确旧远端 OID 的 lease 更新。

个人仓库布局已通过 `git clone --recurse-submodules` 下载验证：19 个模块提交全部匹配，
下载后的源码再次干净构建，真实双栈网络及默认配置回归通过。各 port 的源码和测试可从
总工作区的 submodule 链接进入；缓存、安装工具和生成测试凭据不进入 Git。

## 本地长期 Git 布局

顶层使用标准 `.git/`，19 个模块采用 Git submodule 的 `.git/modules/` 布局。
模块工作目录里的 `.git` 是由 Git 管理的指针文件；每个模块仍有自己的分支、历史和 remote。
Git 元数据不放在 `build/` 或缓存目录中。此次从临时发布目录原地迁移，保留全部分支和 refs；
源码、固定模块提交及之前的运行验证均未改变。

日常修改先在对应模块分支提交并推送，再在顶层提交该模块的新引用。顶层只管理集成文件
和固定版本引用。新克隆的模块通常处于 detached HEAD，开发前切换或创建有明确用途的分支。
清理构建输出不能触碰 `.git/`；备份未推送的本地分支时须包含 `.git/modules/`。
