#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include <ext2fs/ext2fs.h>
#include <ext2fs/kernel-jbd.h>

#define LEO_JOURNAL_BLOCKS 6552U
#define LEO_EXT4_BLOCKS 419329ULL
#define LEO_INODES 104832U

static const unsigned char leo_uuid[16] = {
    0xda, 0x59, 0x4c, 0x53, 0x9b, 0xeb, 0xf8, 0x5c,
    0x85, 0xc5, 0xce, 0xdf, 0x76, 0x54, 0x6f, 0x7a,
};
static const unsigned char leo_label[16] = {
    's', 'y', 's', 't', 'e', 'm', 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
};

static int fail_err(const char *operation, errcode_t error)
{
    com_err("create-leo-journal", error, "%s", operation);
    return 1;
}

int main(int argc, char **argv)
{
    ext2_filsys fs = NULL;
    struct ext2_inode inode;
    journal_superblock_t *journal_super;
    blk64_t journal_block;
    char *journal_data = NULL;
    errcode_t error;
    char *end = NULL;
    unsigned long requested;

    if (argc != 3) {
        fprintf(stderr, "usage: %s <raw-ext4-image> 6552\n", argv[0]);
        return 64;
    }
    errno = 0;
    requested = strtoul(argv[2], &end, 10);
    if (errno || !end || *end || requested != LEO_JOURNAL_BLOCKS) {
        fprintf(stderr, "FAIL: leo journal size must be exactly %u blocks\n",
                LEO_JOURNAL_BLOCKS);
        return 1;
    }

    error = ext2fs_open(argv[1], EXT2_FLAG_RW | EXT2_FLAG_EXCLUSIVE,
                        0, 0, unix_io_manager, &fs);
    if (error)
        return fail_err("opening raw ext4 image", error);
    if (fs->blocksize != 4096 ||
        ext2fs_blocks_count(fs->super) != LEO_EXT4_BLOCKS ||
        fs->super->s_inodes_count != LEO_INODES ||
        fs->super->s_inode_size != 256 ||
        fs->super->s_blocks_per_group != 32768 ||
        fs->super->s_inodes_per_group != 8064 ||
        fs->super->s_reserved_gdt_blocks != 103 ||
        memcmp(fs->super->s_uuid, leo_uuid, sizeof(leo_uuid)) ||
        memcmp(fs->super->s_volume_name, leo_label, sizeof(leo_label)) ||
        fs->super->s_feature_compat !=
            (EXT2_FEATURE_COMPAT_EXT_ATTR | EXT2_FEATURE_COMPAT_RESIZE_INODE) ||
        fs->super->s_feature_incompat !=
            (EXT2_FEATURE_INCOMPAT_FILETYPE | EXT3_FEATURE_INCOMPAT_EXTENTS) ||
        fs->super->s_feature_ro_compat !=
            (EXT2_FEATURE_RO_COMPAT_SPARSE_SUPER |
             EXT2_FEATURE_RO_COMPAT_LARGE_FILE |
             EXT4_FEATURE_RO_COMPAT_GDT_CSUM)) {
        fprintf(stderr, "FAIL: image does not match the locked pre-journal leo profile\n");
        ext2fs_close_free(&fs);
        return 1;
    }
    if (ext2fs_has_feature_journal(fs->super) || fs->super->s_journal_inum) {
        fprintf(stderr, "FAIL: image already has a journal\n");
        ext2fs_close_free(&fs);
        return 1;
    }
    error = ext2fs_read_inode(fs, EXT2_JOURNAL_INO, &inode);
    if (error) {
        ext2fs_close_free(&fs);
        return fail_err("reading reserved journal inode", error);
    }
    if (inode.i_blocks || inode.i_size || inode.i_size_high) {
        fprintf(stderr, "FAIL: reserved journal inode is not empty\n");
        ext2fs_close_free(&fs);
        return 1;
    }

    /* Match the deterministic mke2fs creation clock used by Gate 2. */
    fs->now = 1;
    error = ext2fs_add_journal_inode(fs, LEO_JOURNAL_BLOCKS, 0);
    if (error) {
        ext2fs_close_free(&fs);
        return fail_err("creating exact internal journal", error);
    }
    error = ext2fs_read_inode(fs, EXT2_JOURNAL_INO, &inode);
    if (error)
        goto journal_error;
    error = ext2fs_bmap2(fs, EXT2_JOURNAL_INO, &inode, NULL, 0, 0,
                         NULL, &journal_block);
    if (error)
        goto journal_error;
    error = ext2fs_get_mem(fs->blocksize, &journal_data);
    if (error)
        goto journal_error;
    error = io_channel_read_blk64(fs->io, journal_block, 1, journal_data);
    if (error)
        goto journal_error;
    journal_super = (journal_superblock_t *)journal_data;
    memset(journal_super->s_uuid, 0, sizeof(journal_super->s_uuid));
    error = io_channel_write_blk64(fs->io, journal_block, 1, journal_data);
    if (error)
        goto journal_error;
    ext2fs_free_mem(&journal_data);
    error = ext2fs_flush(fs);
    if (error) {
        ext2fs_close_free(&fs);
        return fail_err("flushing ext4 image", error);
    }
    error = ext2fs_close_free(&fs);
    if (error)
        return fail_err("closing ext4 image", error);

    printf("journal_blocks=%u\n", LEO_JOURNAL_BLOCKS);
    return 0;

journal_error:
    if (journal_data)
        ext2fs_free_mem(&journal_data);
    ext2fs_close_free(&fs);
    return fail_err("normalizing internal journal UUID", error);
}
