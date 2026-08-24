package io.github.leoaudio.shell;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ComponentName;
import android.content.DialogInterface;
import android.content.Intent;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;

public final class MaintenanceActivity extends Activity {
    private static final String SPOTIFY_PACKAGE = "com.spotify.music";
    private final Handler sessionHandler = new Handler(Looper.getMainLooper());
    private TextView sessionStatus;
    private final Runnable sessionTicker = new Runnable() {
        @Override
        public void run() {
            long remainingMillis = MaintenanceSession.remainingMillis();
            if (remainingMillis <= 0L) {
                MaintenanceSession.close();
                finish();
                return;
            }

            long remainingSeconds = (remainingMillis + 999L) / 1000L;
            long minutes = remainingSeconds / 60L;
            long seconds = remainingSeconds % 60L;
            sessionStatus.setText(getString(
                    R.string.maintenance_session_countdown,
                    minutes,
                    seconds));
            sessionHandler.postDelayed(this, Math.min(1000L, remainingMillis));
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        if (!MaintenanceSession.isValid()) {
            finish();
            return;
        }
        setContentView(R.layout.activity_maintenance);
        sessionStatus = findViewById(R.id.maintenance_session_status);

        bindSettingsButton(R.id.open_wifi, Settings.ACTION_WIFI_SETTINGS);
        bindSettingsButton(R.id.open_vpn, Settings.ACTION_VPN_SETTINGS);

        findViewById(R.id.open_spotify_details).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.parse("package:" + SPOTIFY_PACKAGE));
                startActivitySafely(intent);
            }
        });

        Button stockHome = findViewById(R.id.open_stock_home);
        stockHome.setEnabled(true);
        stockHome.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                confirmStockHome();
            }
        });

        findViewById(R.id.open_shell_details).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                Intent intent = new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS);
                intent.setData(Uri.parse("package:" + getPackageName()));
                startActivitySafely(intent);
            }
        });

        findViewById(R.id.close_maintenance).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                MaintenanceSession.close();
                finish();
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (!MaintenanceSession.isValid()) {
            finish();
            return;
        }
        sessionHandler.removeCallbacks(sessionTicker);
        sessionHandler.post(sessionTicker);
    }

    @Override
    protected void onPause() {
        sessionHandler.removeCallbacks(sessionTicker);
        super.onPause();
    }

    @Override
    protected void onDestroy() {
        sessionHandler.removeCallbacksAndMessages(null);
        super.onDestroy();
    }

    private void bindSettingsButton(int viewId, final String action) {
        findViewById(viewId).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                startActivitySafely(new Intent(action));
            }
        });
    }

    private boolean startActivitySafely(Intent intent) {
        try {
            startActivity(intent);
            return true;
        } catch (RuntimeException exception) {
            Toast.makeText(this, R.string.maintenance_action_failed, Toast.LENGTH_LONG).show();
            return false;
        }
    }

    private void confirmStockHome() {
        new AlertDialog.Builder(this)
                .setTitle(R.string.stock_home_confirm_title)
                .setMessage(R.string.stock_home_confirm_message)
                .setNegativeButton(android.R.string.cancel, null)
                .setPositiveButton(R.string.stock_home_confirm_action,
                        new DialogInterface.OnClickListener() {
                            @Override
                            public void onClick(DialogInterface dialog, int which) {
                                Intent intent = new Intent(Intent.ACTION_MAIN);
                                intent.addCategory(Intent.CATEGORY_HOME);
                                intent.setComponent(new ComponentName(
                                        "com.miui.home",
                                        "com.miui.home.launcher.Launcher"));
                                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK
                                        | Intent.FLAG_ACTIVITY_CLEAR_TOP);
                                if (startActivitySafely(intent)) {
                                    MaintenanceSession.close();
                                }
                            }
                        })
                .show();
    }
}
