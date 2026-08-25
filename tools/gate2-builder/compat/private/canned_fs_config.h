#pragma once

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

int load_canned_fs_config(const char* path);
void canned_fs_config(const char* path, int dir, const char* target_out_path,
                      unsigned* uid, unsigned* gid, unsigned* mode,
                      uint64_t* capabilities);

#ifdef __cplusplus
}
#endif
