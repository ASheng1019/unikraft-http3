/* SPDX-License-Identifier: BSD-3-Clause */
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>
#include <stdlib.h>
#include <errno.h>
#include <uk/config.h>
#if CONFIG_LWIP_NETBUF_RECVINFO
#include <lwip/netif.h>
#include <lwip/tcpip.h>
#include <lwip/sys.h>
#endif

static unsigned int cases;
#define REQUIRE(expr)                                                          \
	do {                                                                   \
		if (!(expr)) {                                                 \
			printf("SOCKET_CONTRACTS FAIL line=%d cases=%u\n",     \
			       __LINE__, cases);                               \
			exit(1);                                               \
		}                                                              \
	} while (0)

static socklen_t address(int family, struct sockaddr_storage *storage)
{
	memset(storage, 0, sizeof(*storage));
	if (family == AF_INET) {
		struct sockaddr_in *a = (void *)storage;
		a->sin_family = family;
		a->sin_addr.s_addr = htonl(INADDR_LOOPBACK);
		return sizeof(*a);
	}
	struct sockaddr_in6 *a = (void *)storage;
	a->sin6_family = family;
	a->sin6_addr = in6addr_loopback;
	return sizeof(*a);
}

static void check_guard(const struct sockaddr_storage *storage,
			socklen_t capacity, socklen_t actual,
			socklen_t returned)
{
	const unsigned char *bytes = (const void *)storage;
	size_t copied = capacity < actual ? capacity : actual;

	REQUIRE(returned == actual);
	for (size_t i = copied; i < sizeof(*storage); ++i)
		REQUIRE(bytes[i] == 0xa5);
	++cases;
}

static void family_contracts(int family)
{
	struct sockaddr_storage server_addr, storage;
	socklen_t actual = address(family, &server_addr);
	socklen_t sizes[] = {0, 1, 8, actual, sizeof(storage)};
	int listener = socket(family, SOCK_STREAM, 0);
	socklen_t length = sizeof(server_addr);

	REQUIRE(listener >= 0);
	REQUIRE(bind(listener, (void *)&server_addr, actual) == 0);
	REQUIRE(getsockname(listener, (void *)&server_addr, &length) == 0);
	REQUIRE(length == actual);
	REQUIRE(listen(listener, 4) == 0);
	for (size_t n = 0; n < sizeof(sizes) / sizeof(sizes[0]); ++n) {
		int client = socket(family, SOCK_STREAM, 0), accepted;
		int udp = socket(family, SOCK_DGRAM, 0);
		int sender = socket(family, SOCK_DGRAM, 0);
		struct sockaddr_storage udp_addr;
		char value;

		REQUIRE(client >= 0 && udp >= 0 && sender >= 0);
		REQUIRE(connect(client, (void *)&server_addr, actual) == 0);
		memset(&storage, 0xa5, sizeof(storage));
		length = sizes[n];
		accepted = accept(listener, (void *)&storage, &length);
		REQUIRE(accepted >= 0);
		check_guard(&storage, sizes[n], actual, length);
		memset(&storage, 0xa5, sizeof(storage));
		length = sizes[n];
		REQUIRE(getsockname(client, (void *)&storage, &length) == 0);
		check_guard(&storage, sizes[n], actual, length);
		memset(&storage, 0xa5, sizeof(storage));
		length = sizes[n];
		REQUIRE(getpeername(client, (void *)&storage, &length) == 0);
		check_guard(&storage, sizes[n], actual, length);
		address(family, &udp_addr);
		REQUIRE(bind(udp, (void *)&udp_addr, actual) == 0);
		length = sizeof(udp_addr);
		REQUIRE(getsockname(udp, (void *)&udp_addr, &length) == 0);
		REQUIRE(sendto(sender, "x", 1, 0, (void *)&udp_addr, actual) ==
			1);
		memset(&storage, 0xa5, sizeof(storage));
		length = sizes[n];
		REQUIRE(recvfrom(udp, &value, 1, 0, (void *)&storage,
				 &length) == 1);
		REQUIRE(value == 'x');
		check_guard(&storage, sizes[n], actual, length);
		close(sender);
		close(udp);
		close(accepted);
		close(client);
	}
	close(listener);
}

#if CONFIG_LWIP_NETBUF_RECVINFO
static sys_sem_t mtu_done;
static u16_t saved_mtu;
static int loopback_found;

static void loopback_mtu(void *restore)
{
	struct netif *nf;

	NETIF_FOREACH(nf) {
		if (!ip4_addr_isloopback(netif_ip4_addr(nf)))
			continue;
		if (restore)
			nf->mtu = saved_mtu;
		else {
			loopback_found = 1;
			saved_mtu = nf->mtu;
			nf->mtu = 1280;
		}
		break;
	}
	sys_sem_signal(&mtu_done);
}

static void df_contracts(void)
{
	struct sockaddr_storage dest;
	socklen_t length = address(AF_INET, &dest);
	char payload[1400] = {0};
	struct iovec iov = { .iov_base = payload, .iov_len = sizeof(payload) };
	struct msghdr msg = { .msg_name = &dest, .msg_namelen = length,
		.msg_iov = &iov, .msg_iovlen = 1 };
	int fd = socket(AF_INET, SOCK_DGRAM, 0), mode = IP_PMTUDISC_DO;

	((struct sockaddr_in *)&dest)->sin_port = htons(9999);
	REQUIRE(fd >= 0);
	REQUIRE(sys_sem_new(&mtu_done, 0) == ERR_OK);
	REQUIRE(tcpip_callback_with_block(loopback_mtu, NULL, 1) == ERR_OK);
	sys_arch_sem_wait(&mtu_done, 0);
	REQUIRE(loopback_found);
	REQUIRE(setsockopt(fd, IPPROTO_IP, IP_MTU_DISCOVER, &mode,
			  sizeof(mode)) == 0);
	errno = 0;
	REQUIRE(sendmsg(fd, &msg, 0) == -1 && errno == EMSGSIZE);
	errno = 0;
	REQUIRE(sendto(fd, payload, sizeof(payload), 0, (void *)&dest,
		       length) == -1 && errno == EMSGSIZE);
	REQUIRE(tcpip_callback_with_block(loopback_mtu, &saved_mtu, 1) == ERR_OK);
	sys_arch_sem_wait(&mtu_done, 0);
	sys_sem_free(&mtu_done);
	close(fd);
	puts("UDP_DF_CONTRACTS PASS sendmsg=EMSGSIZE sendto=EMSGSIZE");
}
#endif

int main(void)
{
	setvbuf(stdout, NULL, _IONBF, 0);
	family_contracts(AF_INET);
	family_contracts(AF_INET6);
	REQUIRE(cases == 40);
#if CONFIG_LWIP_NETBUF_RECVINFO
	df_contracts();
#endif
	puts("SOCKET_CONTRACTS PASS cases=40");
	return 0;
}
