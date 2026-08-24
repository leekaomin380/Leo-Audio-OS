package io.github.leoaudio.shell;

import android.annotation.SuppressLint;
import android.annotation.TargetApi;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.os.Build;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import android.window.OnBackInvokedCallback;
import android.window.OnBackInvokedDispatcher;

public final class MainActivity extends Activity {
    private static final String SPOTIFY_PACKAGE = "com.spotify.music";
    private static final int MAINTENANCE_TAPS = 7;
    private static final long MAINTENANCE_WINDOW_MILLIS = 5000L;

    private final GestureGate maintenanceGate =
            new GestureGate(MAINTENANCE_TAPS, MAINTENANCE_WINDOW_MILLIS);

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        if (BuildConfig.HOME_CAPABLE && Build.VERSION.SDK_INT >= 33) {
            BackApi33.register(this);
        }

        TextView leoMark = findViewById(R.id.leo_mark);
        Button openSpotify = findViewById(R.id.open_spotify);

        leoMark.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                if (maintenanceGate.registerTap(SystemClock.elapsedRealtime())) {
                    startActivity(new Intent(MainActivity.this, MaintenanceAuthActivity.class));
                }
            }
        });

        openSpotify.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                launchSpotify();
            }
        });
    }

    @Override
    protected void onResume() {
        super.onResume();
        renderState();
    }

    @SuppressLint("GestureBackNavigation")
    @Override
    public void onBackPressed() {
        if (BuildConfig.HOME_CAPABLE) {
            return;
        }
        super.onBackPressed();
    }

    @TargetApi(33)
    private static final class BackApi33 {
        private BackApi33() {
        }

        static void register(Activity activity) {
            activity.getOnBackInvokedDispatcher().registerOnBackInvokedCallback(
                    OnBackInvokedDispatcher.PRIORITY_DEFAULT,
                    new OnBackInvokedCallback() {
                        @Override
                        public void onBackInvoked() {
                            // A dedicated HOME surface must remain present.
                        }
                    });
        }
    }

    private void renderState() {
        PackageManager packageManager = getPackageManager();
        boolean spotifyInstalled;
        try {
            packageManager.getPackageInfo(SPOTIFY_PACKAGE, 0);
            spotifyInstalled = true;
        } catch (PackageManager.NameNotFoundException exception) {
            spotifyInstalled = false;
        }

        TextView spotifyState = findViewById(R.id.spotify_state);
        Button openSpotify = findViewById(R.id.open_spotify);
        spotifyState.setText(spotifyInstalled
                ? R.string.spotify_ready
                : R.string.spotify_missing);
        openSpotify.setEnabled(spotifyInstalled);

        Intent homeIntent = new Intent(Intent.ACTION_MAIN);
        homeIntent.addCategory(Intent.CATEGORY_HOME);
        ResolveInfo resolvedHome = packageManager.resolveActivity(
                homeIntent, PackageManager.MATCH_DEFAULT_ONLY);
        ComponentName homeComponent = resolvedHome == null || resolvedHome.activityInfo == null
                ? null
                : new ComponentName(resolvedHome.activityInfo.packageName, resolvedHome.activityInfo.name);

        TextView homeState = findViewById(R.id.home_state);
        homeState.setText(getString(
                R.string.current_home,
                homeComponent == null ? getString(R.string.unknown) : homeComponent.flattenToShortString()));

        boolean isDefaultHome = homeComponent != null
                && getPackageName().equals(homeComponent.getPackageName());
        TextView modeState = findViewById(R.id.shell_mode_state);
        if (!BuildConfig.HOME_CAPABLE) {
            modeState.setText(R.string.mode_safe_preview);
        } else {
            modeState.setText(isDefaultHome
                    ? R.string.mode_home_default
                    : R.string.mode_home_not_default);
        }
    }

    private void launchSpotify() {
        Intent launchIntent = getPackageManager().getLaunchIntentForPackage(SPOTIFY_PACKAGE);
        if (launchIntent == null) {
            Toast.makeText(this, R.string.spotify_launch_failed, Toast.LENGTH_LONG).show();
            renderState();
            return;
        }

        launchIntent.addFlags(Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED);
        try {
            startActivity(launchIntent);
        } catch (RuntimeException exception) {
            Toast.makeText(this, R.string.spotify_launch_failed, Toast.LENGTH_LONG).show();
        }
    }
}
