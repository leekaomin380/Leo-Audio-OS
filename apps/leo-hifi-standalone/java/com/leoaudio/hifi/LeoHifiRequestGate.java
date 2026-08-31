package com.leoaudio.hifi;

/** Pure Java transaction rules shared by the Android adapter and host tests. */
public final class LeoHifiRequestGate {
    public static final int MODE = 1, VOLUME = 2;
    public final int kind, value;
    public final long session, generation, startedAt;
    public LeoHifiRequestGate(int kind, int value, LeoHifiState before, long now) {
        this.kind = kind; this.value = value;
        session = before.session; generation = before.generation; startedAt = now;
    }
    public static boolean canStart(LeoHifiState s, long now, boolean permitted,
            boolean busy, int kind, int value) {
        return permitted && !busy && s.available && s.supported && !s.pending
                && s.isFresh(now) && ((kind == MODE && (value == 0 || value == 1))
                || (kind == VOLUME && value >= 0 && value <= 60 && s.active));
    }
    public String parameter() {
        return (kind == MODE ? "leo_hifi_mode=" + (value == 1 ? "true" : "false")
                : "leo_hifi_volume=" + value) + ";leo_hifi_session=" + session + ";leo_hifi_gen=" + generation;
    }
    public boolean accepts(int result, LeoHifiState after, long now) {
        if (result != 0 || now < startedAt || now - startedAt >= LeoHifiState.MAX_AGE_MS
                || !after.available || !after.supported || !after.isFresh(now)
                || after.session != session || (kind == VOLUME ? after.generation != generation : after.generation < generation)
                || "hal_error".equals(after.reason)) return false;
        if (kind == MODE) return after.requested == (value == 1)
                && (value == 1 || (!after.active && ("idle".equals(after.effective)
                    || "speaker".equals(after.effective) || "wired_standard".equals(after.effective))));
        int expected = 213 + (value * 2) / 5;
        return after.active && after.volumeUser == value
                && after.volumeLeft == expected && after.volumeRight == expected;
    }
}
