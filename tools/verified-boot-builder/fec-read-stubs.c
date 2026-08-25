/*
 * The Phase 4 builder uses the Android 7 fec host tool only for deterministic
 * encode and size modes.  Those paths do not call libfec's device-side read
 * API, but the historical single-binary main also contains -E/-V inspection
 * modes.  Modern Debian's android-libfec package exports no usable C symbols,
 * so fail those unused modes closed instead of linking a different-era ABI.
 */

#include <errno.h>

struct fec_handle;
struct fec_ecc_metadata;
struct fec_verity_metadata;

int fec_open(struct fec_handle **handle, const char *path, int mode, int flags,
             int roots) {
    (void)handle;
    (void)path;
    (void)mode;
    (void)flags;
    (void)roots;
    errno = ENOTSUP;
    return -1;
}

int fec_close(struct fec_handle *handle) {
    (void)handle;
    return 0;
}

int fec_verity_get_metadata(struct fec_handle *handle,
                            struct fec_verity_metadata *metadata) {
    (void)handle;
    (void)metadata;
    errno = ENOTSUP;
    return -1;
}

int fec_ecc_get_metadata(struct fec_handle *handle,
                         struct fec_ecc_metadata *metadata) {
    (void)handle;
    (void)metadata;
    errno = ENOTSUP;
    return -1;
}
