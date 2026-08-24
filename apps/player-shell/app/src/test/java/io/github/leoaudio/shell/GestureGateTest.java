package io.github.leoaudio.shell;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public final class GestureGateTest {
    @Test
    public void opensOnlyOnRequiredTap() {
        GestureGate gate = new GestureGate(7, 5000L);
        for (int index = 0; index < 6; index += 1) {
            assertFalse(gate.registerTap(1000L + index * 100L));
        }
        assertTrue(gate.registerTap(1600L));
    }

    @Test
    public void resetsAfterWindowExpires() {
        GestureGate gate = new GestureGate(3, 1000L);
        assertFalse(gate.registerTap(100L));
        assertFalse(gate.registerTap(200L));
        assertFalse(gate.registerTap(1500L));
        assertFalse(gate.registerTap(1600L));
        assertTrue(gate.registerTap(1700L));
    }

    @Test
    public void resetsAfterSuccessfulSequence() {
        GestureGate gate = new GestureGate(2, 1000L);
        assertFalse(gate.registerTap(100L));
        assertTrue(gate.registerTap(200L));
        assertFalse(gate.registerTap(300L));
        assertTrue(gate.registerTap(400L));
    }
}
