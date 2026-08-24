package io.github.leoaudio.shell;

final class GestureGate {
    private final int requiredTaps;
    private final long windowMillis;
    private int tapCount;
    private long firstTapAt;

    GestureGate(int requiredTaps, long windowMillis) {
        this.requiredTaps = requiredTaps;
        this.windowMillis = windowMillis;
    }

    boolean registerTap(long nowMillis) {
        if (tapCount == 0 || nowMillis - firstTapAt > windowMillis) {
            tapCount = 1;
            firstTapAt = nowMillis;
        } else {
            tapCount += 1;
        }

        if (tapCount >= requiredTaps) {
            tapCount = 0;
            firstTapAt = 0;
            return true;
        }
        return false;
    }
}
