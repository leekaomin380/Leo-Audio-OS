package com.android.systemui.leo;
public final class LeoHifiRequestGateTest {
    private static int count;
    private static final String BASE="schema=2;session=123;gen=5;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=0;backend=S24_LE/KHZ_48;fail=0";
    static void ok(boolean b) { count++; if(!b) throw new AssertionError("check " + count); }
    static LeoHifiState state(String s) { return LeoHifiState.parse(s,1000); }
    public static void main(String[] args) {
        LeoHifiState active=state(BASE);
        ok(LeoHifiRequestGate.canStart(active,1000,true,false,2,0));
        ok(!LeoHifiRequestGate.canStart(active,1000,false,false,1,1));
        ok(!LeoHifiRequestGate.canStart(active,1000,true,true,1,1));
        ok(!LeoHifiRequestGate.canStart(active,4001,true,false,1,1));
        ok(!LeoHifiRequestGate.canStart(active,1000,true,false,2,61));
        ok(!LeoHifiRequestGate.canStart(active,1000,true,false,2,-1));
        ok(!LeoHifiRequestGate.canStart(state(BASE.replace("flow=1","flow=0")),1000,true,false,2,0));
        LeoHifiRequestGate volume=new LeoHifiRequestGate(2,0,active,1000);
        ok(volume.parameter().equals("leo_hifi_volume=0"));
        ok(volume.accepts(0,active,1001));
        ok(!volume.accepts(-1,active,1001));
        ok(!volume.accepts(0,state(BASE.replace("213","205")),1001));
        ok(!volume.accepts(0,state(BASE.replace("session=123","session=124")),1001));
        ok(!volume.accepts(0,state(BASE.replace("gen=5","gen=4")),1001));
        ok(!volume.accepts(0,active,4000));
        ok(!volume.accepts(0,state(BASE.replace("fail=0","fail=4")),1001));
        LeoHifiRequestGate on=new LeoHifiRequestGate(1,1,active,1000);
        ok(on.parameter().equals("leo_hifi_mode=true"));
        ok(!on.accepts(0,state(BASE.replace("requested=hifi","requested=standard")),1001));
        ok(on.accepts(0,state(BASE.replace("flow=1","flow=0").replace("effective=hifi_active","effective=idle")),1001));
        LeoHifiRequestGate off=new LeoHifiRequestGate(1,0,active,1000);
        ok(off.parameter().equals("leo_hifi_mode=false"));
        ok(!off.accepts(0,state(BASE.replace("requested=hifi","requested=standard")),1001));
        ok(!off.accepts(0,state(BASE.replace("requested=hifi","requested=standard").replace("flow=1","flow=0")),1001));
        ok(off.accepts(0,state(BASE.replace("requested=hifi","requested=standard").replace("flow=1","flow=0").replace("effective=hifi_active","effective=wired_standard")),1001));
        System.out.println("LeoHifiRequestGateTest: " + count + " passed");
    }
}
