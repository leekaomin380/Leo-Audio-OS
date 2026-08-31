package com.leoaudio.hifi;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.SystemClock;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;

/**
 * Explicit DAC-volume apply. No write on open, drag, close, reconnect or boot.
 *
 * Port of com.android.systemui.leo.LeoHifiVolumeDialog. The view hierarchy, the seek-bar
 * range, the readback rendering and every branch of onStateChanged are transcribed
 * unchanged. The only difference is the host: SystemUIDialog (a SystemUI internal) is
 * replaced by an AlertDialog owned by this activity, because a third-party package cannot
 * draw over the Quick Settings panel.
 *
 * Volume semantics are untouched: progress 0..60 maps in the HAL to 213 + progress*2/5,
 * so 0 is a valid DAC level and NOT mute, and the 237 ceiling is enforced by the gate.
 */
public final class LeoHifiVolumeActivity extends Activity implements LeoHifiController.Callback {

    private LeoHifiController controller;
    private final LeoHifiVolumeSelection selection = new LeoHifiVolumeSelection();
    private AlertDialog dialog;
    private SeekBar slider;
    private Button apply;
    private TextView readback, status;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        LeoHifiMonitorService.start(this);
        controller = LeoHifiController.get(this);

        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        int padding = (int) (24 * getResources().getDisplayMetrics().density + 0.5f);
        layout.setPadding(padding, padding, padding, padding);

        TextView warning = new TextView(this);
        warning.setText(R.string.leo_hifi_volume_warning);
        layout.addView(warning);

        status = new TextView(this);
        layout.addView(status);

        readback = new TextView(this);
        layout.addView(readback);

        slider = new SeekBar(this);
        slider.setMax(60);
        slider.setContentDescription(getString(R.string.leo_hifi_volume_title));
        slider.setProgress(controller.getState().volumeUser);
        layout.addView(slider);

        apply = new Button(this);
        apply.setText(R.string.leo_hifi_apply);
        layout.addView(apply);

        dialog = new AlertDialog.Builder(this)
                .setTitle(R.string.leo_hifi_volume_title)
                .setView(layout)
                .setNegativeButton(android.R.string.cancel, (d, which) -> d.dismiss())
                .setOnDismissListener(d -> finish())
                .create();

        slider.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            public void onProgressChanged(SeekBar bar, int progress, boolean fromUser) {
                selection.onProgressChanged(progress, fromUser);
                if (fromUser) onStateChanged(controller.getState());
            }
            public void onStartTrackingTouch(SeekBar bar) {}
            public void onStopTrackingTouch(SeekBar bar) {}
        });

        apply.setOnClickListener(view -> {
            LeoHifiState s = controller.getState();
            long now = SystemClock.elapsedRealtime();
            if (selection.canApply(s, now)) {
                selection.onApply();
                apply.setEnabled(false);
                controller.requestVolume(selection.getProgress()); // zero is valid, NOT mute
            }
        });

        controller.addCallback(this);
        dialog.show();
        onStateChanged(controller.getState());
    }

    @Override
    protected void onDestroy() {
        if (controller != null) controller.removeCallback(this);
        if (dialog != null && dialog.isShowing()) dialog.dismiss();
        super.onDestroy();
    }

    @Override
    public void onStateChanged(LeoHifiState s) {
        if (slider == null || s == null) return;
        long now = SystemClock.elapsedRealtime();
        selection.onStateChanged(s, now);
        if (slider.getProgress() != selection.getProgress()) {
            slider.setProgress(selection.getProgress());
        }
        boolean ready = s.available && s.supported && s.active && !s.pending && s.isFresh(now);
        slider.setEnabled(ready);
        apply.setEnabled(selection.canApply(s, now));
        status.setText(s.pending ? R.string.leo_hifi_waiting
                : "request_failed".equals(s.reason) || "request_rejected".equals(s.reason)
                ? R.string.leo_hifi_error : ready ? R.string.leo_hifi_active : R.string.leo_hifi_not_active);
        readback.setText(s.available ? getString(R.string.leo_hifi_volume_readback,
                slider.getProgress(), s.volumeLeft, s.volumeRight)
                : getString(R.string.leo_hifi_no_readback));
    }
}
