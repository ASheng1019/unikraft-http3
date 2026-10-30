/* SPDX-License-Identifier: BSD-3-Clause */
/* Test-only input flags; reject any delivery of flagged input to QUIC. */
#include <sys/socket.h>
#include <ngtcp2/ngtcp2.h>
#include <stdio.h>
#include <stdlib.h>

extern ssize_t __real_recvmsg(int, struct msghdr *, int);
extern int __real_ngtcp2_pkt_decode_version_cid(ngtcp2_version_cid *,
						const uint8_t *, size_t,
						size_t);
static unsigned int injected, skipped;
static int pending;

ssize_t __wrap_recvmsg(int fd, struct msghdr *msg, int flags)
{
	ssize_t count;

	if (pending) {
		pending = 0;
		if (++skipped == 2)
			puts("TEST_RX_FLAGS PASS skipped=2 parser_calls=0");
	}
	count = __real_recvmsg(fd, msg, flags);
	if (injected < 2 && count >= 1200 && msg->msg_iovlen == 1 &&
	    (((const unsigned char *)msg->msg_iov[0].iov_base)[0] & 0xc0) ==
		0xc0) {
		msg->msg_flags |= injected++ ? MSG_CTRUNC : MSG_TRUNC;
		pending = 1;
	}
	return count;
}

int __wrap_ngtcp2_pkt_decode_version_cid(ngtcp2_version_cid *dest,
					 const uint8_t *data, size_t datalen,
					 size_t short_dcidlen)
{
	if (pending) {
		puts("TEST_RX_FLAGS FAIL truncated_input_reached_QUIC");
		abort();
	}
	return __real_ngtcp2_pkt_decode_version_cid(dest, data, datalen,
						    short_dcidlen);
}
