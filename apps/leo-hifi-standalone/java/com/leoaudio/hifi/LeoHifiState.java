package com.leoaudio.hifi;

import java.util.HashMap;
import java.util.Map;

public final class LeoHifiState {
    public static final long MAX_AGE_MS = 3000;

    public final boolean available;
    public final boolean supported;
    public final boolean requested;
    public final boolean active;
    public final boolean pending;
    public final int volumeUser;
    public final int volumeLeft;
    public final int volumeRight;
    public final long session;
    public final long generation;
    public final long observedAtElapsedMs;
    public final String effective;
    public final String reason;
    public final String backend;

    private LeoHifiState(boolean available, boolean supported, boolean requested,
                         boolean active, boolean pending, int volumeUser,
                         int volumeLeft, int volumeRight, long session,
                         long generation, long observedAtElapsedMs,
                         String effective, String reason, String backend) {
        this.available = available;
        this.supported = supported;
        this.requested = requested;
        this.active = active;
        this.pending = pending;
        this.volumeUser = volumeUser;
        this.volumeLeft = volumeLeft;
        this.volumeRight = volumeRight;
        this.session = session;
        this.generation = generation;
        this.observedAtElapsedMs = observedAtElapsedMs;
        this.effective = effective != null ? effective : "idle";
        this.reason = reason != null ? reason : "";
        this.backend = backend != null ? backend : "unconfirmed";
    }

    public static LeoHifiState unavailable(String reason, long now) {
        return new LeoHifiState(false, false, false, false, false, 0, 0, 0, -1, -1, now, "idle", reason, "unconfirmed");
    }

    public static LeoHifiState parse(String wire, long now) {
        if (wire == null || wire.length() == 0 || wire.length() > 2048) {
            return unavailable("empty_or_oversize", now);
        }

        String payload = wire;
        if (payload.startsWith("leo_hifi_status=")) {
            payload = payload.substring("leo_hifi_status=".length());
        }

        if (payload.trim().isEmpty()) {
            return unavailable("empty_payload", now);
        }

        Map<String, String> map = new HashMap<>();
        String[] pairs = payload.split(";", -1);
        for (String pair : pairs) {
            if (pair.isEmpty()) {
                return unavailable("empty_pair", now);
            }
            int eq = pair.indexOf('=');
            if (eq <= 0 || eq == pair.length() - 1 || pair.indexOf('=', eq + 1) >= 0) {
                return unavailable("malformed_pair", now);
            }
            String k = pair.substring(0, eq);
            String v = pair.substring(eq + 1);
            if (!k.matches("[a-zA-Z0-9_]+") || !v.matches("[a-zA-Z0-9_./x-]+")) return unavailable("invalid_token", now);
            if (map.containsKey(k)) {
                return unavailable("duplicate_key", now);
            }
            map.put(k, v);
        }

        try {
            if (!"3".equals(map.get("schema"))) return unavailable("invalid_schema", now);

            String sessionStr = map.get("session");
            if (sessionStr == null) return unavailable("missing_session", now);
            if (!sessionStr.matches("[0-9]+")) return unavailable("invalid_session", now);
            long session = Long.parseLong(sessionStr);
            if (session <= 0) return unavailable("invalid_session", now);

            String genStr = map.get("gen");
            if (genStr == null) return unavailable("missing_gen", now);
            if (!genStr.matches("[0-9]+")) return unavailable("invalid_gen", now);
            long gen = Long.parseLong(genStr);
            if (gen < 0) return unavailable("invalid_gen", now);

            String suppStr = map.get("supported");
            if (!"0".equals(suppStr) && !"1".equals(suppStr)) return unavailable("invalid_supported", now);
            boolean supported = "1".equals(suppStr);

            String reqStr = map.get("requested");
            if (!"hifi".equals(reqStr) && !"standard".equals(reqStr)) return unavailable("invalid_requested", now);
            boolean requested = "hifi".equals(reqStr);

            String effStr = map.get("effective");
            if (!"idle".equals(effStr) && !"speaker".equals(effStr) &&
                !"wired_standard".equals(effStr) && !"arming".equals(effStr) &&
                !"hifi_active".equals(effStr) && !"hifi_degraded".equals(effStr) &&
                !"error_fallback".equals(effStr)) {
                return unavailable("invalid_effective", now);
            }

            String liveStr = map.get("live");
            if (!"0".equals(liveStr) && !"1".equals(liveStr)) return unavailable("invalid_live", now);
            boolean live = "1".equals(liveStr);

            String flowStr = map.get("flow");
            if (!"0".equals(flowStr) && !"1".equals(flowStr)) return unavailable("invalid_flow", now);
            boolean flow = "1".equals(flowStr);

            String vlStr = map.get("vol_ctl_l");
            String vrStr = map.get("vol_ctl_r");
            if (vlStr == null || vrStr == null) return unavailable("missing_vol_ctl", now);
            int volL = Integer.parseInt(vlStr);
            int volR = Integer.parseInt(vrStr);

            String vuStr = map.get("vol_user");
            if (vuStr == null) return unavailable("missing_vol_user", now);
            int volUser = Integer.parseInt(vuStr);
            if (volUser < 0 || volUser > 60) return unavailable("invalid_vol_user", now);

            String backendStr = map.get("backend");
            if (!"S24_LE/KHZ_48".equals(backendStr) && !"unconfirmed".equals(backendStr)) {
                return unavailable("invalid_backend", now);
            }

            String failStr = map.get("fail");
            if (failStr == null) return unavailable("missing_fail", now);
            long fail = Long.parseLong(failStr);
            if (fail < 0) return unavailable("invalid_fail", now);

            boolean active = supported &&
                    "hifi_active".equals(effStr) &&
                    live &&
                    flow &&
                    (volL == volR) &&
                    (volL >= 205 && volL <= 237) &&
                    "S24_LE/KHZ_48".equals(backendStr) &&
                    (fail == 0);

            return new LeoHifiState(true, supported, requested, active, false,
                    volUser, volL, volR, session, gen, now, effStr, fail == 0 ? "parsed" : "hal_error", backendStr);
        } catch (NumberFormatException e) {
            return unavailable("number_format_error", now);
        }
    }

    public boolean isFresh(long now) {
        long age = now - observedAtElapsedMs;
        return age >= 0 && age <= MAX_AGE_MS;
    }

    public LeoHifiState withPending(boolean value, String reason) {
        return new LeoHifiState(available, supported, requested, active, value,
                volumeUser, volumeLeft, volumeRight, session, generation,
                observedAtElapsedMs, effective, reason, backend);
    }

    public LeoHifiState withReason(String newReason) {
        return new LeoHifiState(available, supported, requested, active, pending,
                volumeUser, volumeLeft, volumeRight, session, generation,
                observedAtElapsedMs, effective, newReason, backend);
    }
}
