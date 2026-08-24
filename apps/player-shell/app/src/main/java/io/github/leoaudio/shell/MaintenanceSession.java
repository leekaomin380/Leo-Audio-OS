package io.github.leoaudio.shell;

import android.os.SystemClock;

final class MaintenanceSession {
    private static final long SESSION_MILLIS = 5L * 60L * 1000L;
    private static long expiresAt;

    private MaintenanceSession() {
    }

    static synchronized void open() {
        expiresAt = SystemClock.elapsedRealtime() + SESSION_MILLIS;
    }

    static synchronized boolean isValid() {
        return remainingMillis() > 0L;
    }

    static synchronized long remainingMillis() {
        return Math.max(0L, expiresAt - SystemClock.elapsedRealtime());
    }

    static synchronized void close() {
        expiresAt = 0L;
    }
}
