/* SPDX-License-Identifier: BSD-3-Clause */
/* Test-only alternate platform time: exercises real POSIX paths, no app libc
 * wrappers. This is not a platform RTC implementation or deployment feature.
 */
#include "../../app-nghttpx/deployment.h"
#include <stdint.h>
#include <stdio.h>
#include <uk/plat/time.h>
static uint64_t epoch_offset;
__nsec __wrap_ukplat_wall_clock(void)
{
	return ukplat_monotonic_clock() + epoch_offset;
}
int main(void)
{
	unsigned long long epoch;
	char extra;
	FILE *f = fopen("/test-platform-epoch.txt", "r");
	if (f) {
		int count = fscanf(f, "%llu %c", &epoch, &extra);
		fclose(f);
		if (count != 1 || epoch < 1704067200 || epoch > 4102444800ULL)
			return 1;
		epoch_offset = epoch * 1000000000ULL - ukplat_monotonic_clock();
	}
	return app_nghttpx_run();
}
