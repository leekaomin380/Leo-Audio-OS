package com.leoaudio.hifi;

import android.app.KeyguardManager;
import android.content.Context;
import android.content.SharedPreferences;
import android.media.AudioManager;
import android.os.Build;
import android.os.Handler;
import android.os.HandlerThread;
import android.os.Looper;
import android.os.SystemClock;
import android.os.UserManager;
import android.util.Log;
import java.lang.reflect.Method;
import java.util.ArrayList;

/**
 * Standalone port of the SystemUI-resident controller. HAL remains the only mixer writer.
 * No exported entry point.
 *
 * Deltas from com.android.systemui.leo.LeoHifiController, each deliberate:
 *
 *  1. android.media.AudioSystem (@hide) is replaced by android.media.AudioManager, whose
 *     get/setParameters are public SDK API over the same AudioFlinger path. AudioFlinger
 *     gates that path on MODIFY_AUDIO_SETTINGS, which is protectionLevel=normal on this
 *     ROM, so no privileged status is required to drive schema3.
 *
 *  2. AudioManager.setParameters returns void, so the int status AudioSystem.setParameters
 *     returned is not available. LeoHifiRequestGate.accepts() uses that status only as a
 *     fast-fail; every substantive check after it is a readback proof (session equality,
 *     generation match/advance, requested-value match, exact dual-channel volume readback,
 *     effective-state match, freshness). We still recover the true status by reflection when
 *     hidden-API access is permitted (system/priv-app, or a relaxed hidden_api_policy) and
 *     fall back to 0 otherwise. WRITE_STATUS_UNAVAILABLE records which path was taken so the
 *     acceptance evidence can state whether a real status code backed it.
 *
 *  3. ActivityManager.getCurrentUser() == 0 is dropped: it is @hide, and in SystemUI it
 *     guarded a process that persists across user switches. This app's process is bound to
 *     its own user, and ownerProcess() already requires that user to be the system user, so
 *     the foreground-user check is redundant here. The keyguard and user-unlocked guards are
 *     retained verbatim.
 */
public final class LeoHifiController {
    private static final String TAG = "LeoHifi";
    private static LeoHifiController sInstance;
    private static final String SAVED = "confirmed_enable";

    /** True once a write has gone out without a real AudioFlinger status code behind it. */
    public static volatile boolean WRITE_STATUS_UNAVAILABLE = false;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final Handler worker;
    private final Context context;
    private final AudioManager audio;
    private final SharedPreferences prefs;
    private final ArrayList<Callback> callbacks = new ArrayList<>();
    private volatile LeoHifiState state = LeoHifiState.unavailable("initializing", now());
    // Main-thread confined. A hung Binder occupies ONE worker. A timeout does
    // not cancel a HAL write already in progress: its result must be reconciled.
    private boolean busy, expired, restoreAttempted;
    private long session, operation;
    private LeoHifiRequestGate deferredUserRequest; // At most one intent, bound to its original identity/deadline.
    private final Runnable poll = () -> begin(null);
    private final Runnable expiry = () -> {
        if (!state.isFresh(now())) publish(LeoHifiState.unavailable("stale", now()));
    };

    public interface Callback { void onStateChanged(LeoHifiState state); }

    public static synchronized LeoHifiController get(Context context) {
        if (sInstance == null) sInstance = new LeoHifiController(context.getApplicationContext());
        return sInstance;
    }

    private LeoHifiController(Context context) {
        this.context = context;
        this.audio = context.getSystemService(AudioManager.class);
        prefs = context.createDeviceProtectedStorageContext()
                .getSharedPreferences("leo_hifi", Context.MODE_PRIVATE);
        HandlerThread thread = new HandlerThread("LeoHifi");
        thread.start(); worker = new Handler(thread.getLooper());
        if ("leo".equals(Build.DEVICE) && ownerProcess()) main.post(poll);
    }

    private static long now() { return SystemClock.elapsedRealtime(); }

    public LeoHifiState getState() { return state; }

    public void addCallback(Callback cb) {
        main.post(() -> { if (!callbacks.contains(cb)) callbacks.add(cb); cb.onStateChanged(state); });
    }

    public void removeCallback(Callback cb) { main.post(() -> callbacks.remove(cb)); }

    public void refresh() { main.post(() -> begin(null)); }

    public void requestEnabled(boolean enabled) { request(LeoHifiRequestGate.MODE, enabled ? 1 : 0); }

    public void requestVolume(int value) { request(LeoHifiRequestGate.VOLUME, value); }

    /**
     * Delta 4: the original compared Process.myUserHandle() against UserHandle.SYSTEM, which
     * is @hide. userId is uid / PER_USER_RANGE and PER_USER_RANGE is 100000 on every Android
     * release, so dividing the public Process.myUid() yields the same answer with public API
     * only: this process belongs to the system user (userId 0).
     */
    private static boolean ownerProcess() {
        return android.os.Process.myUid() / 100000 == 0;
    }

    private boolean permitted() {
        try {
            KeyguardManager keyguard = context.getSystemService(KeyguardManager.class);
            UserManager users = context.getSystemService(UserManager.class);
            return ownerProcess() && "leo".equals(Build.DEVICE)
                    && users != null && users.isUserUnlocked()
                    && keyguard != null && !keyguard.isDeviceLocked();
        } catch (RuntimeException e) { return false; }
    }

    // ---- HAL access -------------------------------------------------------
    // Read is public SDK. Write prefers the hidden AudioSystem.setParameters for its int
    // status and degrades to the public AudioManager.setParameters, which returns void.

    private static Method sSetParameters;
    private static boolean sSetParametersResolved;

    private String halRead() { return audio.getParameters("leo_hifi_status"); }

    private int halWrite(String keyValuePairs) {
        if (!sSetParametersResolved) {
            sSetParametersResolved = true;
            try {
                Class<?> as = Class.forName("android.media.AudioSystem");
                sSetParameters = as.getMethod("setParameters", String.class);
            } catch (Throwable t) {
                sSetParameters = null;
                Log.i(TAG, "AudioSystem.setParameters unavailable; using AudioManager (no status code)");
            }
        }
        if (sSetParameters != null) {
            try {
                Object r = sSetParameters.invoke(null, keyValuePairs);
                if (r instanceof Integer) return (Integer) r;
            } catch (Throwable t) {
                sSetParameters = null;
                Log.i(TAG, "AudioSystem.setParameters invocation blocked; falling back", t);
            }
        }
        WRITE_STATUS_UNAVAILABLE = true;
        audio.setParameters(keyValuePairs);
        return 0; // Readback in LeoHifiRequestGate.accepts() carries the proof.
    }

    // ---- transaction ------------------------------------------------------

    private void request(int kind, int value) {
        main.post(() -> {
            boolean waitingForRead = busy && !state.pending && !expired;
            if (!LeoHifiRequestGate.canStart(state, now(), permitted(),
                    busy && !waitingForRead, kind, value) || deferredUserRequest != null) {
                if (!busy) publish(state.withReason("request_rejected"));
                return;
            }
            restoreAttempted = true;
            LeoHifiRequestGate intent = new LeoHifiRequestGate(kind, value, state, now());
            if (waitingForRead) {
                deferredUserRequest = intent;
                publish(state.withPending(true, "waiting_for_status"));
            } else begin(intent);
        });
    }

    private void begin(LeoHifiRequestGate request) {
        if (busy || !ownerProcess() || !"leo".equals(Build.DEVICE)) return;
        main.removeCallbacks(poll); busy = true; expired = false;
        final long id = ++operation, started = now();
        if (request != null) publish(state.withPending(true, "requesting"));
        final Runnable timeout = () -> {
            if (busy && operation == id) {
                expired = true;
                deferredUserRequest = null;
                publish(LeoHifiState.unavailable("timeout_reconcile_required", now()));
            }
        };
        main.postDelayed(timeout, LeoHifiState.MAX_AGE_MS);
        worker.post(() -> {
            int result = 0;
            LeoHifiState after;
            try {
                if (request != null) {
                    LeoHifiState before = LeoHifiState.parse(halRead(), now());
                    // Recheck immediately before Binder; never replay a queued write after unlock/user changes.
                    if (!permitted() || now() - request.startedAt >= LeoHifiState.MAX_AGE_MS
                            || before.session != request.session || before.generation != request.generation
                            || !LeoHifiRequestGate.canStart(before, now(), true, false, request.kind, request.value)) {
                        result = -1;
                    } else result = halWrite(request.parameter());
                }
                after = LeoHifiState.parse(halRead(), now());
            } catch (RuntimeException | LinkageError e) {
                result = -1; after = LeoHifiState.unavailable("audio_service_error", now());
            }
            final int code = result;
            final LeoHifiState snapshot = after;
            main.post(() -> {
                main.removeCallbacks(timeout);
                if (id != operation) return;
                busy = false;
                if (expired || now() - started >= LeoHifiState.MAX_AGE_MS) {
                    deferredUserRequest = null;
                    publish(LeoHifiState.unavailable("reconciling", now()));
                    main.post(poll); return; // Never acknowledge a late operation.
                }
                boolean changed = snapshot.available && session != 0 && session != snapshot.session;
                if (snapshot.available) session = snapshot.session;
                if (changed) {
                    deferredUserRequest = null;
                    restoreAttempted = false;
                    publish(LeoHifiState.unavailable("audio_service_restarted", now()));
                } else {
                    boolean accepted = request != null && request.accepts(code, snapshot, now());
                    if (accepted && request.kind == LeoHifiRequestGate.MODE)
                        prefs.edit().putBoolean(SAVED, request.value == 1).apply();
                    publish(request != null && !accepted ? snapshot.withReason("request_failed") : snapshot);
                    if (request == null && deferredUserRequest != null) {
                        LeoHifiRequestGate queued = deferredUserRequest;
                        deferredUserRequest = null;
                        if (queued.session == snapshot.session && queued.generation == snapshot.generation
                                && now() >= queued.startedAt
                                && now() - queued.startedAt < LeoHifiState.MAX_AGE_MS
                                && LeoHifiRequestGate.canStart(snapshot, now(), permitted(), false,
                                        queued.kind, queued.value)) {
                            begin(queued); return;
                        }
                        publish(snapshot.withReason("request_rejected"));
                    }
                    if (request == null && snapshot.available && snapshot.supported
                            && !restoreAttempted && permitted()) {
                        restoreAttempted = true;
                        boolean saved = prefs.getBoolean(SAVED, false);
                        if (snapshot.requested != saved) {
                            begin(new LeoHifiRequestGate(LeoHifiRequestGate.MODE, saved ? 1 : 0, snapshot, now()));
                            return;
                        }
                    }
                }
                main.postDelayed(poll, 1000);
            });
        });
    }

    private void publish(LeoHifiState snapshot) {
        state = snapshot; main.removeCallbacks(expiry);
        if (snapshot.available) main.postDelayed(expiry,
                Math.max(0, snapshot.observedAtElapsedMs + LeoHifiState.MAX_AGE_MS + 1 - now()));
        for (Callback cb : new ArrayList<>(callbacks)) {
            try { cb.onStateChanged(snapshot); }
            catch (RuntimeException e) { Log.w(TAG, "UI callback failed", e); }
        }
    }
}
