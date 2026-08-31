#define main legacy_main
#include "legacy_controller.c"
#undef main

static void active_card(void) {
    card_default(); init_enabled(); apply_hifi_path(); leo_hifi_on_route(&lh, true);
}
static void floor_ok(const char *why) {
    ok(why, mock_get_int("Volume", 0) == 205 && mock_get_int("Volume", 1) == 205
       && !lh.vol_applied && !lh.vol_restore_pending);
}
static void wire(FILE *f, const char *label) {
    char buf[512];
    ok("serializer succeeds", leo_hifi_status_string(&lh, buf, sizeof(buf)) == 0);
    fprintf(f, "%s\tleo_hifi_status=%s\n", label, buf);
}
int main(int argc, char **argv) {
    if (argc != 2) return 2;
    if (legacy_main()) return 1;
    initialized = 0; /* legacy_main destroyed its mutex */
    FILE *f = fopen(argv[1], "w");
    if (!f) return 2;

    active_card();
    floor_ok("entry never replays saved gain");
    ok("explicit gain works", leo_hifi_apply_volume(&lh, 30) == 0);
    leo_hifi_set_mode(&lh, false);
    floor_ok("OFF restores both channels without needing XML reset");

    active_card(); leo_hifi_apply_volume(&lh, 30); leo_hifi_on_route_off(&lh);
    floor_ok("route exit restores without XML reset");
    active_card(); leo_hifi_apply_volume(&lh, 30); leo_hifi_on_route(&lh, false);
    floor_ok("ordinary route restores without XML reset");

    active_card(); leo_hifi_apply_volume(&lh, 30);
    mock_fail_write("Volume", 1);
    ok("failed restore returns EIO", leo_hifi_restore_volume_floor(&lh) == -EIO);
    ok("failed restore retains dirty state", lh.vol_applied && lh.vol_restore_pending
       && mock_get_int("Volume", 0) == 225);
    wire(f, "restoring");
    ok("cannot apply another gain while recovery pending", leo_hifi_apply_volume(&lh, 0) == -EIO);
    ok("cannot select HiFi while recovery fails", !leo_hifi_route_wanted(&lh));
    mock_fail_write("Volume", 0);
    leo_hifi_on_route_off(&lh);
    floor_ok("later route exit retries previously failed restore");

    active_card(); leo_hifi_apply_volume(&lh, 30);
    mock_skew_readback("Volume", 1);
    ok("unproven restore remains pending", leo_hifi_restore_volume_floor(&lh) == -EIO
       && lh.vol_restore_pending && lh.vol_applied);
    mock_skew_readback("Volume", 0); leo_hifi_on_route_off(&lh);
    floor_ok("verified readback releases pending recovery");

    active_card(); leo_hifi_apply_volume(&lh, 30);
    // NO card_default: emulate a HAL restart with hardware and saved intent retained.
    init_enabled();
    floor_ok("new HAL session resets retained hardware gain, not mock baseline");
    ok("new session does not replay saved user volume", lh.vol_user == 30);

    active_card(); mock_set_int("Volume", 213, 225);
    ok("asymmetric channels at target cannot falsely succeed", leo_hifi_apply_volume(&lh, 0) == -EIO);
    floor_ok("asymmetric starting state recovers both channels");

    active_card();
    unsigned long long token = leo_hifi_flow_token(&lh);
    leo_hifi_note_frames(&lh, token, 1, 1024, 1024, 512, true);
    leo_hifi_note_frames(&lh, token, 1, 1536, 1024, 512, true);
    leo_hifi_note_frames(&lh, token, 1, 2048, 1024, 512, true);
    wire(f, "active");
    char full[512], tiny[512];
    leo_hifi_status_string(&lh, full, sizeof(full));
    size_t n = strlen(full);
    for (size_t len = 1; len <= n; ++len) {
        memset(tiny, 'X', sizeof(tiny));
        if (leo_hifi_status_string(&lh, tiny, len) != -ENOSPC || tiny[0] != 0) {
            ok("all truncated buffers fail closed", 0); break;
        }
        if (len == n) ok("all truncated buffers fail closed", 1);
    }
    ok("exact full buffer accepted", leo_hifi_status_string(&lh, tiny, n + 1) == 0);
    ok("zero/null output rejected", leo_hifi_status_string(&lh, NULL, 0) == -EINVAL);
    lh.session = 9223372036854775807ULL; lh.generation = 9223372036854775807ULL;
    wire(f, "max_identity");
    lh.generation = 3;
    leo_hifi_set_mode(&lh, false); leo_hifi_on_route_off(&lh);
    wire(f, "idle");
    fclose(f);
    leo_hifi_destroy(&lh); ess_present(0);
    printf("DAILY SAFETY: %d passed, %d failed\n", g_pass, g_fail);
    return g_fail ? 1 : 0;
}
