package com.android.systemui.leo;
import android.os.*; import android.media.AudioSystem; import android.content.Context; import android.app.*;
public final class J152TransactionTest {
 static int checks; static void ok(boolean c){checks++;if(!c)throw new AssertionError("check "+checks);}
 static void round(){Handler.main();Handler.worker();Handler.main();}
 static String active="schema=3;session=123;gen=5;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=0;backend=S24_LE/KHZ_48;fail=0";
 static void reset(LeoHifiController c){AudioSystem.wire=active;c.refresh();round();if(!c.getState().available){c.refresh();round();}AudioSystem.writes.clear();}
 public static void main(String[] args){
  Context context=new Context();context.prefs.saved=true;AudioSystem.wire=active;
  LeoHifiController c=LeoHifiController.get(context);round();ok(c.getState().active);
  c.refresh();c.requestVolume(30);Handler.main();ok(c.getState().pending);ok(AudioSystem.writes.size()==0);
  for(int i=0;i<100;i++)c.requestVolume(40);Handler.main();ok(Handler.workerCount()==1);
  Handler.worker();Handler.main();ok(Handler.workerCount()==1);Handler.worker();Handler.main();
  ok(AudioSystem.writes.size()==1);ok(AudioSystem.writes.get(0).startsWith("leo_hifi_volume=30;"));
  reset(c);c.refresh();c.requestVolume(0);Handler.main();AudioSystem.wire=active.replace("gen=5","gen=6");
  Handler.worker();Handler.main();ok(AudioSystem.writes.isEmpty());ok(!c.getState().pending);ok("request_rejected".equals(c.getState().reason));
  reset(c);c.refresh();c.requestVolume(0);Handler.main();KeyguardManager.locked=true;Handler.worker();Handler.main();
  ok(AudioSystem.writes.isEmpty());KeyguardManager.locked=false;
  reset(c);c.refresh();c.requestVolume(0);Handler.main();Handler.advance(4000);ok(!c.getState().available);
  Handler.worker();Handler.main();ok(AudioSystem.writes.isEmpty());round();ok(AudioSystem.writes.isEmpty());
  reset(c);c.requestEnabled(false);Handler.main();AudioSystem.wire=active.replace("gen=5","gen=6");
  Handler.worker();Handler.main();ok(AudioSystem.writes.isEmpty()); // pre-write MODE identity remains exact
  reset(c);c.refresh();c.requestVolume(0);Handler.main();AudioSystem.wire=active.replace("session=123","session=124");
  Handler.worker();Handler.main();ok(AudioSystem.writes.isEmpty());ok(!c.getState().available);
  reset(c);c.refresh();c.requestVolume(0);Handler.main();Handler.worker();Handler.main();Handler.worker();Handler.main();
  ok(AudioSystem.writes.size()==1);ok(AudioSystem.writes.get(0).contains("leo_hifi_session=123;leo_hifi_gen=5"));
  LeoHifiVolumeSelection s=new LeoHifiVolumeSelection();s.onStateChanged(c.getState(),SystemClock.elapsedRealtime());s.onProgressChanged(40,true);s.onApply();ok(!s.isTouched());
  System.out.println("J152TransactionTest: "+checks+" passed (bounded poll queue; stale/locked/expired intents never replayed)");
 }
}
