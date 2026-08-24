package io.github.leoaudio.shell;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Base64;

import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Arrays;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

final class PinStore {
    private static final String PREFERENCES = "maintenance_auth";
    private static final String KEY_SALT = "pin_salt";
    private static final String KEY_HASH = "pin_hash";
    private static final int ITERATIONS = 120_000;
    private static final int KEY_BITS = 256;
    private static final int SALT_BYTES = 16;

    private final SharedPreferences preferences;

    PinStore(Context context) {
        preferences = context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE);
    }

    boolean isConfigured() {
        return preferences.contains(KEY_SALT) && preferences.contains(KEY_HASH);
    }

    boolean save(char[] pin) {
        byte[] salt = new byte[SALT_BYTES];
        new SecureRandom().nextBytes(salt);
        byte[] hash = derive(pin, salt);
        if (hash == null) {
            Arrays.fill(salt, (byte) 0);
            return false;
        }

        boolean saved = preferences.edit()
                .putString(KEY_SALT, Base64.encodeToString(salt, Base64.NO_WRAP))
                .putString(KEY_HASH, Base64.encodeToString(hash, Base64.NO_WRAP))
                .commit();
        Arrays.fill(salt, (byte) 0);
        Arrays.fill(hash, (byte) 0);
        return saved;
    }

    boolean verify(char[] pin) {
        String saltValue = preferences.getString(KEY_SALT, null);
        String hashValue = preferences.getString(KEY_HASH, null);
        if (saltValue == null || hashValue == null) {
            return false;
        }

        byte[] salt;
        byte[] expected;
        try {
            salt = Base64.decode(saltValue, Base64.NO_WRAP);
            expected = Base64.decode(hashValue, Base64.NO_WRAP);
        } catch (IllegalArgumentException exception) {
            return false;
        }

        byte[] actual = derive(pin, salt);
        boolean matches = actual != null && MessageDigest.isEqual(expected, actual);
        Arrays.fill(salt, (byte) 0);
        Arrays.fill(expected, (byte) 0);
        if (actual != null) {
            Arrays.fill(actual, (byte) 0);
        }
        return matches;
    }

    private static byte[] derive(char[] pin, byte[] salt) {
        PBEKeySpec keySpec = new PBEKeySpec(pin, salt, ITERATIONS, KEY_BITS);
        try {
            SecretKeyFactory factory = SecretKeyFactory.getInstance("PBKDF2WithHmacSHA1");
            return factory.generateSecret(keySpec).getEncoded();
        } catch (Exception exception) {
            return null;
        } finally {
            keySpec.clearPassword();
        }
    }
}
