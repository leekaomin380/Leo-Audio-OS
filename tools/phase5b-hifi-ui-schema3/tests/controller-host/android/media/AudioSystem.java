package android.media;
import java.util.*;
public class AudioSystem {
 public static String wire; public static boolean ignore; public static int result;
 public static Runnable nextRead,nextWrite; public static List<String> writes=new ArrayList<>();
 public static String getParameters(String key){if(nextRead!=null){Runnable r=nextRead;nextRead=null;r.run();}return wire;}
 public static int setParameters(String p){writes.add(p);if(nextWrite!=null){Runnable r=nextWrite;nextWrite=null;r.run();}
 if(!ignore&&result==0){if(p.startsWith("leo_hifi_mode=false;"))wire=wire.replace("requested=hifi","requested=standard").replace("effective=hifi_active","effective=wired_standard").replace("flow=1","flow=0");
 else if(p.startsWith("leo_hifi_mode=true;"))wire=wire.replace("requested=standard","requested=hifi");}
 return result;}
}
