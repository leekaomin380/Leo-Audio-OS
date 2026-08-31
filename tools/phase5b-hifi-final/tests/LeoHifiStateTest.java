package com.android.systemui.leo;

import java.util.function.Predicate;

public class LeoHifiStateTest {

    private static int passed = 0;
    private static int failed = 0;

    public static void main(String[] args) {
        String validBase = "schema=3;session=123;gen=5;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=210;vol_ctl_r=210;vol_user=40;backend=S24_LE/KHZ_48;fail=0";

        check("Happy path valid", validBase, 1000, s -> s.available && s.active && s.requested && s.session == 123);
        check("Optional prefix", "leo_hifi_status=" + validBase, 1000, s -> s.available && s.active);
        check("Unknown unique keys allowed", validBase + ";extra_key=xyz", 1000, s -> s.available);

        String reqStandard = validBase.replace("requested=hifi", "requested=standard");
        check("Requested standard but active", reqStandard, 1000, s -> s.available && s.active && !s.requested);

        check("Not active if live=0", validBase.replace("live=1", "live=0"), 1000, s -> s.available && !s.active);
        check("Not active if flow=0", validBase.replace("flow=1", "flow=0"), 1000, s -> s.available && !s.active);
        check("Not active if fail=1", validBase.replace("fail=0", "fail=1"), 1000, s -> s.available && !s.active);
        check("Not active if volume L!=R", validBase.replace("vol_ctl_r=210", "vol_ctl_r=211"), 1000, s -> s.available && !s.active);
        check("Not active if volume out of range (<205)", validBase.replace("vol_ctl_l=210;vol_ctl_r=210", "vol_ctl_l=204;vol_ctl_r=204"), 1000, s -> s.available && !s.active);
        check("Not active if volume out of range (>237)", validBase.replace("vol_ctl_l=210;vol_ctl_r=210", "vol_ctl_l=238;vol_ctl_r=238"), 1000, s -> s.available && !s.active);
        check("Not active if effective!=hifi_active", validBase.replace("effective=hifi_active", "effective=speaker"), 1000, s -> s.available && !s.active && "speaker".equals(s.effective));
        check("Not active if backend!=S24_LE/KHZ_48", validBase.replace("backend=S24_LE/KHZ_48", "backend=unconfirmed"), 1000, s -> s.available && !s.active);
        check("Not active if supported=0", validBase.replace("supported=1", "supported=0"), 1000, s -> s.available && !s.active);

        check("Missing schema", validBase.replace("schema=3;", ""), 1000, s -> !s.available);
        check("Missing session", validBase.replace("session=123;", ""), 1000, s -> !s.available);

        check("Reject previous schema 2", validBase.replace("schema=3", "schema=2"), 1000, s -> !s.available);
        check("Legacy schema 1", validBase.replace("schema=3", "schema=1"), 1000, s -> !s.available);

        check("Malformed pair no equals", "schema3;session=123", 1000, s -> !s.available);
        check("Malformed double semicolon", validBase.replace("gen=5;", "gen=5;;"), 1000, s -> !s.available);
        check("Duplicate keys", validBase + ";gen=6", 1000, s -> !s.available);
        check("Empty string", "", 1000, s -> !s.available);
        check("Null safety", null, 1000, s -> !s.available);

        check("Negative session", validBase.replace("session=123", "session=-1"), 1000, s -> !s.available);
        check("Zero session", validBase.replace("session=123", "session=0"), 1000, s -> !s.available);
        check("Negative gen", validBase.replace("gen=5", "gen=-1"), 1000, s -> !s.available);
        check("Negative fail", validBase.replace("fail=0", "fail=-1"), 1000, s -> !s.available);
        check("Invalid supported enum", validBase.replace("supported=1", "supported=2"), 1000, s -> !s.available);
        check("Invalid live enum", validBase.replace("live=1", "live=true"), 1000, s -> !s.available);
        check("Invalid volume user (>60)", validBase.replace("vol_user=40", "vol_user=61"), 1000, s -> !s.available);
        check("Invalid volume user (<0)", validBase.replace("vol_user=40", "vol_user=-1"), 1000, s -> !s.available);

        check("Overflow session", validBase.replace("session=123", "session=99999999999999999999999"), 1000, s -> !s.available);
        StringBuilder sb = new StringBuilder("schema=3");
        for (int i=0; i<3000; i++) sb.append(";k").append(i).append("=v");
        check("Oversize string", sb.toString(), 1000, s -> !s.available);

        LeoHifiState s1 = LeoHifiState.parse(validBase, 1000);
        assertTrue("Fresh at same time", s1.isFresh(1000));
        assertTrue("Fresh at 3999", s1.isFresh(3999));
        assertTrue("Fresh at MAX_AGE", s1.isFresh(4000));
        assertTrue("Stale after MAX_AGE", !s1.isFresh(4001));
        assertTrue("Time went backwards", !s1.isFresh(999));

        LeoHifiState s2 = s1.withPending(true, "user_click");
        assertTrue("withPending sets pending", s2.pending);
        assertTrue("withPending keeps observed time", s2.observedAtElapsedMs == 1000);
        assertTrue("withPending stale after MAX_AGE", !s2.isFresh(4001));

        System.out.println("LeoHifiStateTest: " + passed + " passed, " + failed + " failed");
        if (failed > 0) {
            System.err.println(failed + " TESTS FAILED.");
            System.exit(1);
        }
    }

    private static void check(String name, String wire, long now, Predicate<LeoHifiState> cond) {
        LeoHifiState state = LeoHifiState.parse(wire, now);
        if (cond.test(state)) passed++;
        else {
            failed++;
            System.err.println("FAILED: " + name + " | state=" + state.reason);
        }
    }

    private static void assertTrue(String msg, boolean cond) {
        if (cond) passed++;
        else {
            failed++;
            System.err.println("FAILED ASSERT: " + msg);
        }
    }
}
