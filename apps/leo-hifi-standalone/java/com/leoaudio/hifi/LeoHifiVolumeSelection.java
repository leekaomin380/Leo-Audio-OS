package com.leoaudio.hifi;

public final class LeoHifiVolumeSelection {
    private boolean touched;
    private int progress;
    private long lastSession = -1;
    private long lastGen = -1;

    public void onProgressChanged(int newProgress, boolean fromUser) {
        if (fromUser) {
            touched = true;
            progress = newProgress;
        }
    }

    public void onStateChanged(LeoHifiState s, long now) {
        boolean ready = s.available && s.supported && s.active && !s.pending && s.isFresh(now);
        if (!ready || s.session != lastSession || s.generation != lastGen) {
            touched = false;
            lastSession = s.session;
            lastGen = s.generation;
        }
        if (ready && !touched) {
            progress = s.volumeUser;
        }
    }

    public boolean canApply(LeoHifiState s, long now) {
        return touched && s.session == lastSession && s.generation == lastGen && s.available && s.supported && s.active && !s.pending && s.isFresh(now);
    }

    public void onApply() {
        touched = false;
    }

    public int getProgress() {
        return progress;
    }

    public boolean isTouched() {
        return touched;
    }
}
