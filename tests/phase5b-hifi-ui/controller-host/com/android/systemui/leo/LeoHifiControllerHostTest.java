package com.android.systemui.leo;
import android.os.*; import android.media.AudioSystem; import android.content.Context; import android.app.*;
public final class LeoHifiControllerHostTest {
 static int checks; static void ok(boolean c){checks++;if(!c)throw new AssertionError("check "+checks);}
 static void round(){Handler.main();Handler.worker();Handler.main();}
 static void poll(){Handler.advance(1000);round();}
 static String active="schema=2;session=123;gen=5;supported=1;requested=hifi;effective=hifi_active;live=1;flow=1;vol_ctl_l=213;vol_ctl_r=213;vol_user=0;backend=S24_LE/KHZ_48;fail=0";
 public static void main(String[] args){
 Context context=new Context(); context.prefs.saved=true; AudioSystem.wire=active;
 LeoHifiController c=LeoHifiController.get(context); round();
 ok(context.deviceProtected);ok(c.getState().active);ok(AudioSystem.writes.size()==0);
 KeyguardManager.locked=true;c.requestEnabled(false);round();ok(AudioSystem.writes.size()==0);
 KeyguardManager.locked=false;ActivityManager.user=10;c.requestVolume(0);round();ok(AudioSystem.writes.size()==0);
 ActivityManager.user=0;UserManager.unlocked=false;c.requestEnabled(false);round();ok(AudioSystem.writes.size()==0);
 android.os.Process.owner=false;UserManager.unlocked=true;c.requestEnabled(false);round();ok(AudioSystem.writes.size()==0);
 android.os.Process.owner=true;UserManager.unlocked=true;c.requestVolume(61);round();ok(AudioSystem.writes.size()==0);
 c.requestEnabled(false);Handler.main();ok(c.getState().pending);
 for(int i=0;i<100;i++){c.refresh();c.requestEnabled(true);}Handler.main();ok(Handler.workerCount()==1);
 Handler.worker();Handler.main();ok(!c.getState().requested);ok(!context.prefs.saved);ok(context.prefs.writes==1);
 AudioSystem.ignore=true;c.requestEnabled(true);round();ok(!c.getState().requested);ok(context.prefs.writes==1);ok(c.getState().reason.equals("request_failed"));
 AudioSystem.ignore=false;AudioSystem.wire=active;poll();ok(c.getState().active);
 int before=context.prefs.writes;
 AudioSystem.nextWrite=()->Handler.advance(4000);
 c.requestEnabled(false);round();ok(!c.getState().available);ok(context.prefs.writes==before);
 ok(Handler.workerCount()==1);round();ok(c.getState().available);ok(!c.getState().requested);
 AudioSystem.wire=active;poll();ok(c.getState().active);
 AudioSystem.nextRead=()->Handler.advance(4000);poll();ok(!c.getState().available);ok(Handler.workerCount()==1);round();ok(c.getState().active);
 AudioSystem.wire=active.replace("session=123","session=124");poll();ok(!c.getState().available);ok(c.getState().reason.equals("audio_service_restarted"));
 // Preference is false: fresh supported read in the new session restores OFF, never volume.
 poll();round();ok(!c.getState().requested);
 for(String p:AudioSystem.writes)ok(!p.startsWith("leo_hifi_volume="));
 AudioSystem.wire="garbage";poll();ok(!c.getState().available);
 int writes=AudioSystem.writes.size();c.requestEnabled(true);round();ok(AudioSystem.writes.size()==writes);
 System.out.println("LeoHifiControllerHostTest: "+checks+" passed (virtual scheduler / fake Android; not device runtime)");
 }
}
