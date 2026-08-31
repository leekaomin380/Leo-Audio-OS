package com.android.systemui.leo;

public final class J141VolumeSelectionTest {
    private static int checks;
    static void ok(boolean b) { checks++; if (!b) throw new AssertionError("check " + checks); }
    public static void main(String[] args) {
        LeoHifiVolumeSelection sel = new LeoHifiVolumeSelection();
        LeoHifiState active = LeoHifiState.parse("schema=3;session=100;gen=10;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=15;backend=S24_LE/KHZ_48;fail=0", 1000);
        sel.onStateChanged(active, 1000);
        ok(sel.getProgress() == 15);
        ok(!sel.canApply(active, 1000));
        
        sel.onProgressChanged(20, true);
        ok(sel.getProgress() == 20);
        ok(sel.canApply(active, 1000));
        
        LeoHifiState nextGen = LeoHifiState.parse("schema=3;session=100;gen=11;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=15;backend=S24_LE/KHZ_48;fail=0", 1000);
        sel.onStateChanged(nextGen, 1000);
        ok(!sel.canApply(nextGen, 1000));
        ok(sel.getProgress() == 15);
        
        sel.onProgressChanged(30, true);
        ok(!sel.canApply(active, 1000)); // generation differs even before callback
        LeoHifiState anotherSession = LeoHifiState.parse("schema=3;session=101;gen=11;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=5;backend=S24_LE/KHZ_48;fail=0", 1000);
        ok(!sel.canApply(anotherSession, 1000));
        sel.onStateChanged(anotherSession,1000); ok(sel.getProgress()==5 && !sel.isTouched());
        sel.onProgressChanged(0,true); ok(sel.canApply(anotherSession,1000));
        sel.onStateChanged(anotherSession,4001); ok(!sel.isTouched());
        sel.onStateChanged(anotherSession,1000); ok(sel.getProgress()==5);
        sel.onProgressChanged(20,true);
        sel.onStateChanged(anotherSession.withPending(true,"test"),1000); ok(!sel.isTouched());
        sel.onStateChanged(LeoHifiState.unavailable("test",1000),1000); ok(!sel.canApply(anotherSession,1000));
                System.out.println("J141VolumeSelectionTest passed: " + checks);
    }
}
