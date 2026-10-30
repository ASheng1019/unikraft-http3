/* SPDX-License-Identifier: BSD-3-Clause */
/* Test-only link wrapper. The production port contains no injection switch. */
#include <sys/socket.h>
#include <sys/uio.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

extern ssize_t __real_sendmsg(int, const struct msghdr *, int);
static unsigned failures, armed, completed;
static int saved_fd;
static unsigned char packet[65536], saved[65536], control[512],
    remote[sizeof(struct sockaddr_storage)];
static size_t saved_len, control_len, remote_len;

ssize_t __wrap_sendmsg(int fd, const struct msghdr *msg, int flags)
{
	size_t len = 0;
	for (size_t i = 0; i < msg->msg_iovlen; ++i) {
		size_t n = msg->msg_iov[i].iov_len;
		if (n > sizeof(packet) - len)
			return __real_sendmsg(fd, msg, flags);
		memcpy(packet + len, msg->msg_iov[i].iov_base, n);
		len += n;
	}
	/* QUIC short-header packets exercise Http3Upstream's blocked TX path.
	 */
	if (!armed && !completed && len > 32 && (packet[0] & 0xc0) == 0x40 &&
	    msg->msg_namelen <= sizeof(remote) &&
	    msg->msg_controllen <= sizeof(control)) {
		int type = 0;
		socklen_t type_len = sizeof(type);
		if (getsockopt(fd, SOL_SOCKET, SO_TYPE, &type, &type_len) ==
			0 &&
		    type == SOCK_DGRAM) {
			armed = 1;
			saved_fd = fd;
			saved_len = len;
			remote_len = msg->msg_namelen;
			control_len = msg->msg_controllen;
			memcpy(saved, packet, len);
			if (remote_len)
				memcpy(remote, msg->msg_name, remote_len);
			if (control_len)
				memcpy(control, msg->msg_control, control_len);
		}
	}
	if (armed && fd == saved_fd && len == saved_len &&
	    msg->msg_namelen == remote_len &&
	    msg->msg_controllen == control_len && !memcmp(saved, packet, len) &&
	    (!remote_len || !memcmp(remote, msg->msg_name, remote_len)) &&
	    (!control_len || !memcmp(control, msg->msg_control, control_len))) {
		if (failures < 3) {
			++failures;
			errno = EAGAIN;
			return -1;
		}
		ssize_t n = __real_sendmsg(fd, msg, flags);
		if (n == (ssize_t)len) {
			armed = 0;
			completed = 1;
			puts("TEST_UDP_EAGAIN PASS failures=3 "
			     "identical_datagram_and_metadata=1");
		}
		return n;
	}
	return __real_sendmsg(fd, msg, flags);
}
