package io.github.leoaudio.shell;

import static org.junit.Assert.assertEquals;

import org.junit.After;
import org.junit.Test;

public final class AuthThrottleTest {
    @After
    public void resetThrottle() {
        AuthThrottle.reset();
    }

    @Test
    public void locksOnFifthFailure() {
        assertEquals(4, AuthThrottle.recordFailure(1000L));
        assertEquals(3, AuthThrottle.recordFailure(1100L));
        assertEquals(2, AuthThrottle.recordFailure(1200L));
        assertEquals(1, AuthThrottle.recordFailure(1300L));
        assertEquals(0, AuthThrottle.recordFailure(1400L));
        assertEquals(30_000L, AuthThrottle.remainingLockoutMillis(1400L));
    }

    @Test
    public void lockoutSurvivesRepeatedChecksUntilDeadline() {
        for (int index = 0; index < 5; index += 1) {
            AuthThrottle.recordFailure(1000L + index);
        }
        assertEquals(1L, AuthThrottle.remainingLockoutMillis(31_003L));
        assertEquals(0L, AuthThrottle.remainingLockoutMillis(31_004L));
        assertEquals(4, AuthThrottle.recordFailure(31_005L));
    }

    @Test
    public void successResetRestoresFullAttemptBudget() {
        assertEquals(4, AuthThrottle.recordFailure(1000L));
        assertEquals(3, AuthThrottle.recordFailure(1100L));
        AuthThrottle.reset();
        assertEquals(4, AuthThrottle.recordFailure(1200L));
    }
}
