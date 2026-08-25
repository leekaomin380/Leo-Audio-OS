FROM debian:bookworm-slim@sha256:abd67ffcfa541b485a3dff59865ab629aa048a6c613e639d36e7456b0b229241

ARG SYSTEM_EXTRAS_REV=aa3f820033cfaf3a61d1e3cc617309ae652f0c4f
ARG SYSTEM_CORE_REV=88f64719d75620d144af5bba39a00a3f178ae60a
ARG EXTERNAL_FEC_REV=791afbe58ff9f55145c4adf632ab8cc9ca6e5686

RUN apt-get -qq update \
    && apt-get -qq install -y --no-install-recommends \
        android-libbase-dev \
        android-libcutils-dev \
        android-libext4-utils-dev \
        android-libsparse-dev \
        build-essential \
        ca-certificates \
        git \
        libssl-dev \
        zlib1g-dev \
    && rm -rf /var/lib/apt/lists/*

RUN mkdir -p /src/system-extras /src/system-core /src/external-fec \
    && cd /src/system-extras \
    && git init -q \
    && git remote add origin https://android.googlesource.com/platform/system/extras \
    && git fetch -q --depth=1 origin "$SYSTEM_EXTRAS_REV" \
    && git checkout -q --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$SYSTEM_EXTRAS_REV" \
    && cd /src/system-core \
    && git init -q \
    && git remote add origin https://android.googlesource.com/platform/system/core \
    && git fetch -q --depth=1 origin "$SYSTEM_CORE_REV" \
    && git checkout -q --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$SYSTEM_CORE_REV" \
    && cd /src/external-fec \
    && git init -q \
    && git remote add origin https://android.googlesource.com/platform/external/fec \
    && git fetch -q --depth=1 origin "$EXTERNAL_FEC_REV" \
    && git checkout -q --detach FETCH_HEAD \
    && test "$(git rev-parse HEAD)" = "$EXTERNAL_FEC_REV"

COPY compat-modern-libsparse.patch /tmp/compat-modern-libsparse.patch
COPY fec-read-stubs.c /tmp/fec-read-stubs.c

RUN cd /src/system-extras \
    && git apply --check /tmp/compat-modern-libsparse.patch \
    && git apply /tmp/compat-modern-libsparse.patch \
    && cd /src/external-fec \
    && gcc -O3 -fPIC -c init_rs_char.c encode_rs_char.c decode_rs_char.c \
    && ar rcs /tmp/libfec_rs.a init_rs_char.o encode_rs_char.o decode_rs_char.o \
    && gcc -O2 -c /tmp/fec-read-stubs.c -o /tmp/fec-read-stubs.o \
    && cd /src/system-extras \
    && multiarch="$(dpkg-architecture -qDEB_HOST_MULTIARCH)" \
    && g++ -std=gnu++11 -O2 -Wall \
        -I/usr/include/android \
        -o /usr/local/bin/build_verity_tree \
        verity/build_verity_tree.cpp \
        -L"/usr/lib/$multiarch/android" \
        -Wl,-rpath,"/usr/lib/$multiarch/android" \
        -Wl,--build-id=none \
        -lsparse -lbase -lcrypto -lz \
    && g++ -std=gnu++11 -O3 -Wall \
        -I/src/external-fec \
        -I/src/system-core/include \
        -I/src/system-extras/libfec/include \
        -I/usr/include/android \
        -Iverity/fec \
        -o /usr/local/bin/fec \
        verity/fec/main.cpp \
        verity/fec/image.cpp \
        /tmp/libfec_rs.a \
        /tmp/fec-read-stubs.o \
        -L"/usr/lib/$multiarch/android" \
        -Wl,-rpath,"/usr/lib/$multiarch/android" \
        -Wl,--build-id=none \
        -lsparse -lbase -lcrypto -lz -lpthread \
    && test "$(/usr/local/bin/build_verity_tree -s 1717571584)" = 13533184 \
    && test "$(/usr/local/bin/fec -s 1731137536)" = 13692928

ENTRYPOINT ["/bin/sh"]
