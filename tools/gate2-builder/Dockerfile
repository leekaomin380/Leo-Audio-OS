FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

ARG E2FSPROGS_REV=ef148046cf58dc1009da35ed9edb7a7425e19f39

RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends \
        android-libcutils-dev \
        android-libsparse-dev \
        build-essential \
        ca-certificates \
        git \
        libselinux1-dev \
        libssl-dev \
        pkg-config \
        selinux-utils \
        zlib1g-dev

RUN git clone https://android.googlesource.com/platform/external/e2fsprogs /src/e2fsprogs \
    && cd /src/e2fsprogs \
    && git checkout --detach "$E2FSPROGS_REV" \
    && ./configure --disable-nls --enable-elf-shlibs --prefix=/opt/e2fsprogs \
    && make -j"$(nproc)" \
    && make install

COPY compat /opt/leo-e2fsdroid-compat

RUN gcc \
        -I/src/e2fsprogs \
        -I/src/e2fsprogs/lib \
        -I/src/e2fsprogs/lib/ext2fs \
        -I/src/e2fsprogs/misc \
        -I/src/e2fsprogs/contrib/android \
        -I/opt/leo-e2fsdroid-compat \
        -I/usr/include/android \
        -o /usr/local/bin/e2fsdroid \
        /src/e2fsprogs/contrib/android/e2fsdroid.c \
        /src/e2fsprogs/contrib/android/block_range.c \
        /src/e2fsprogs/contrib/android/fsmap.c \
        /src/e2fsprogs/contrib/android/block_list.c \
        /src/e2fsprogs/contrib/android/base_fs.c \
        /src/e2fsprogs/contrib/android/perms.c \
        /src/e2fsprogs/contrib/android/basefs_allocator.c \
        /src/e2fsprogs/misc/create_inode.c \
        /opt/leo-e2fsdroid-compat/no_copy_xattrs.c \
        -L/opt/e2fsprogs/lib \
        -L/usr/lib/aarch64-linux-gnu/android \
        -Wl,-rpath,/opt/e2fsprogs/lib:/usr/lib/aarch64-linux-gnu/android \
        -lext2fs -le2p -lcom_err -lsparse -lcutils -lselinux -lcrypto -lz -luuid -lblkid \
    && test -x /usr/local/bin/e2fsdroid

ENTRYPOINT ["/bin/sh"]
