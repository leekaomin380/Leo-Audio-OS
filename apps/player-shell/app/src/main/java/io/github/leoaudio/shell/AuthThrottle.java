package io.github.leoaudio.shell;

final class AuthThrottle {
    private static final int MAX_FAILURES = 5;
    private static final long LOCKOUT_MILLIS = 30_000L;

    private static int failedAttempts;
    private static long lockedUntil;

    private AuthThrottle() {
    }

    static synchronized long remainingLockoutMillis(long nowMillis) {
        return Math.max(0L, lockedUntil - nowMillis);
    }

    static synchronized int recordFailure(long nowMillis) {
        if (remainingLockoutMillis(nowMillis) > 0L) {
            return 0;
        }
        failedAttempts += 1;
        if (failedAttempts >= MAX_FAILURES) {
            failedAttempts = 0;
            lockedUntil = nowMillis + LOCKOUT_MILLIS;
            return 0;
        }
        return MAX_FAILURES - failedAttempts;
    }

    static synchronized void reset() {
        failedAttempts = 0;
        lockedUntil = 0L;
    }
}
