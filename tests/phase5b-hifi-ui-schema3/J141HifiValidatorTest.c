#include <stdio.h>
#include <stdbool.h>
#include <string.h>
#include <errno.h>
#include <assert.h>
#include "leo_hifi.h"

int main() {
    struct leo_hifi lh;
    memset(&lh, 0, sizeof(lh));
    lh.session = 100;
    lh.generation = 5;
    lh.requested = true;
    lh.effective = 4; /* LEO_HIFI_ACTIVE */
    lh.supported = true;
    lh.fail_code = 0; /* LEO_FAIL_NONE */
    pthread_mutex_init(&lh.telemetry_lock, NULL);
    
    bool changed = false;
    
    // 1. Missing session/gen -> -EINVAL
    assert(leo_hifi_process_request(&lh, "true", NULL, NULL, NULL, &changed) == -EINVAL);
    // 2. Both mode and volume -> -EINVAL
    assert(leo_hifi_process_request(&lh, "true", "30", "100", "5", &changed) == -EINVAL);
    // 3. Invalid session/gen format -> -EINVAL
    assert(leo_hifi_process_request(&lh, "true", NULL, "malformed", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, "true", NULL, "-1", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, "true", NULL, "0", "5", &changed) == -EINVAL);
    // 4. Stale session/gen -> -EAGAIN
    assert(leo_hifi_process_request(&lh, "true", NULL, "99", "5", &changed) == -EAGAIN);
    assert(leo_hifi_process_request(&lh, "true", NULL, "100", "4", &changed) == -EAGAIN);
    
    // 5. Volume formatting
    assert(leo_hifi_process_request(&lh, NULL, "60x", "100", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, NULL, "+0", "100", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, NULL, "-1", "100", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, NULL, "00", "100", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, NULL, "61", "100", "5", &changed) == -EINVAL);
    assert(leo_hifi_process_request(&lh, NULL, "999999999999999999999", "100", "5", &changed) == -EINVAL);
    
    // 6. Mode formatting
    assert(leo_hifi_process_request(&lh, "tru", NULL, "100", "5", &changed) == -EINVAL);
    
    // 7. No op
    assert(leo_hifi_process_request(&lh, NULL, NULL, "100", "5", &changed) == -EINVAL);

    pthread_mutex_destroy(&lh.telemetry_lock);
    printf("J141 C Validator: 15 boundary checks passed.\n");
    return 0;
}
