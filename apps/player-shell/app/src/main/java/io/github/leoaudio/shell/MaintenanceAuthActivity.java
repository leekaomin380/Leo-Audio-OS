package io.github.leoaudio.shell;

import android.app.Activity;
import android.content.Intent;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import java.util.Arrays;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MaintenanceAuthActivity extends Activity {
    private static final int PIN_LENGTH = 6;
    private PinStore pinStore;
    private EditText pinEntry;
    private EditText pinConfirmation;
    private TextView authMessage;
    private Button submitButton;
    private final ExecutorService cryptoExecutor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Runnable lockoutTicker = new Runnable() {
        @Override
        public void run() {
            long remainingMillis = AuthThrottle.remainingLockoutMillis(
                    SystemClock.elapsedRealtime());
            if (remainingMillis <= 0L) {
                setLockoutUi(false);
                renderMode();
                return;
            }

            long seconds = Math.max(1L, (remainingMillis + 999L) / 1000L);
            setLockoutUi(true);
            authMessage.setText(getString(R.string.pin_locked, seconds));
            mainHandler.postDelayed(this, Math.min(1000L, remainingMillis));
        }
    };

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_maintenance_auth);

        pinStore = new PinStore(this);
        pinEntry = findViewById(R.id.pin_entry);
        pinConfirmation = findViewById(R.id.pin_confirmation);
        authMessage = findViewById(R.id.auth_message);
        submitButton = findViewById(R.id.submit_pin);

        renderMode();
        if (AuthThrottle.remainingLockoutMillis(SystemClock.elapsedRealtime()) > 0L) {
            startLockoutCountdown();
        }
        submitButton.setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                submit();
            }
        });
        findViewById(R.id.cancel_auth).setOnClickListener(new View.OnClickListener() {
            @Override
            public void onClick(View view) {
                finish();
            }
        });
    }

    private void renderMode() {
        boolean setup = !pinStore.isConfigured();
        pinConfirmation.setVisibility(setup ? View.VISIBLE : View.GONE);
        authMessage.setText(setup ? R.string.pin_setup_message : R.string.pin_unlock_message);
        submitButton.setText(setup ? R.string.pin_setup_action : R.string.pin_unlock_action);
    }

    private void submit() {
        long now = SystemClock.elapsedRealtime();
        long remainingLockout = AuthThrottle.remainingLockoutMillis(now);
        if (remainingLockout > 0L) {
            long seconds = Math.max(1L, (remainingLockout + 999L) / 1000L);
            authMessage.setText(getString(R.string.pin_locked, seconds));
            return;
        }

        char[] pin = pinEntry.getText().toString().toCharArray();
        if (!validPin(pin)) {
            Arrays.fill(pin, '\0');
            authMessage.setText(R.string.pin_invalid_format);
            return;
        }

        if (!pinStore.isConfigured()) {
            char[] confirmation = pinConfirmation.getText().toString().toCharArray();
            try {
                if (!Arrays.equals(pin, confirmation)) {
                    Arrays.fill(pin, '\0');
                    authMessage.setText(R.string.pin_mismatch);
                    return;
                }
            } finally {
                Arrays.fill(confirmation, '\0');
                pinConfirmation.setText("");
            }

            runCrypto(pin, true);
            return;
        }

        runCrypto(pin, false);
    }

    private void runCrypto(final char[] pin, final boolean setup) {
        mainHandler.removeCallbacks(lockoutTicker);
        setBusy(true, setup ? R.string.pin_saving : R.string.pin_verifying);
        cryptoExecutor.execute(new Runnable() {
            @Override
            public void run() {
                boolean result;
                try {
                    result = setup ? pinStore.save(pin) : pinStore.verify(pin);
                } catch (RuntimeException exception) {
                    result = false;
                } finally {
                    Arrays.fill(pin, '\0');
                }
                final boolean success = result;

                mainHandler.post(new Runnable() {
                    @Override
                    public void run() {
                        if (isFinishing() || isDestroyed()) {
                            return;
                        }
                        handleCryptoResult(setup, success);
                    }
                });
            }
        });
    }

    private void handleCryptoResult(boolean setup, boolean success) {
        setBusy(false, setup ? R.string.pin_setup_message : R.string.pin_unlock_message);
        if (success) {
            AuthThrottle.reset();
            openMaintenance();
            return;
        }

        if (setup) {
            authMessage.setText(R.string.pin_storage_failed);
            return;
        }

        pinEntry.setText("");
        int remainingAttempts = AuthThrottle.recordFailure(SystemClock.elapsedRealtime());
        if (remainingAttempts == 0) {
            startLockoutCountdown();
        } else {
            authMessage.setText(getString(
                    R.string.pin_wrong,
                    remainingAttempts));
        }
    }

    private void setBusy(boolean busy, int messageResource) {
        submitButton.setEnabled(!busy);
        pinEntry.setEnabled(!busy);
        pinConfirmation.setEnabled(!busy);
        authMessage.setText(messageResource);
    }

    private void startLockoutCountdown() {
        mainHandler.removeCallbacks(lockoutTicker);
        mainHandler.post(lockoutTicker);
    }

    private void setLockoutUi(boolean locked) {
        submitButton.setEnabled(!locked);
        pinEntry.setEnabled(!locked);
        pinConfirmation.setEnabled(!locked);
        if (locked) {
            pinEntry.setText("");
            pinConfirmation.setText("");
        }
    }

    @Override
    protected void onDestroy() {
        mainHandler.removeCallbacksAndMessages(null);
        cryptoExecutor.shutdownNow();
        super.onDestroy();
    }

    private boolean validPin(char[] pin) {
        if (pin.length != PIN_LENGTH) {
            return false;
        }
        for (char character : pin) {
            if (character < '0' || character > '9') {
                return false;
            }
        }
        return true;
    }

    private void openMaintenance() {
        pinEntry.setText("");
        MaintenanceSession.open();
        startActivity(new Intent(this, MaintenanceActivity.class));
        finish();
    }
}
