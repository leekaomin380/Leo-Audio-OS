package com.leoaudio.hifi;

import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.os.IBinder;
import android.os.SystemClock;
import android.util.Log;

public final class LeoHifiMonitorService extends Service implements LeoHifiController.Callback {
    private LeoHifiNotifications notifications;
    private LeoHifiController controller;
    public static void start(Context context) {
        if (!"leo".equals(Build.DEVICE) || android.os.Process.myUid() / 100000 != 0) return;
        try { context.startForegroundService(new Intent(context, LeoHifiMonitorService.class)); }
        catch (RuntimeException e) { Log.w("LeoHifi", "Monitor unavailable", e); }
    }
    @Override public void onCreate() {
        super.onCreate();
        notifications = new LeoHifiNotifications(this);
        notifications.clearActive();
        startForeground(LeoHifiNotifications.MONITOR_ID, notifications.observer());
        controller = LeoHifiController.get(this);
        controller.addCallback(this);
    }
    @Override public int onStartCommand(Intent intent, int flags, int startId) {
        controller.refresh();
        return START_STICKY;
    }
    @Override public void onStateChanged(LeoHifiState state) {
        notifications.update(state, SystemClock.elapsedRealtime());
    }
    @Override public void onDestroy() {
        if (controller != null) controller.removeCallback(this);
        if (notifications != null) notifications.clearActive();
        stopForeground(STOP_FOREGROUND_REMOVE);
        super.onDestroy();
    }
    @Override public IBinder onBind(Intent intent) { return null; }
}
