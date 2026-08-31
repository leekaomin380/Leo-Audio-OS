package android.os;
import java.util.*;
public class Handler {
 public static long now=1000; private final Looper loop;
 private static final List<Task> tasks=new ArrayList<>();
 private static class Task { Handler h; Runnable r; long at; Task(Handler h,Runnable r,long at){this.h=h;this.r=r;this.at=at;} }
 public Handler(Looper l){loop=l;} public boolean post(Runnable r){return postDelayed(r,0);}
 public boolean postDelayed(Runnable r,long ms){tasks.add(new Task(this,r,now+ms));return true;}
 public void removeCallbacks(Runnable r){tasks.removeIf(t->t.h==this&&t.r==r);}
 public static void main(){int n=0; while(run(true)){if(++n>1000)throw new AssertionError("main loop runaway");}}
 public static void worker(){run(false);}
 private static boolean run(boolean main){for(Task t:new ArrayList<>(tasks)){if((t.h.loop==Looper.MAIN)==main&&t.at<=now){tasks.remove(t);t.r.run();return true;}}return false;}
 public static void advance(long ms){now+=ms;main();}
 public static int workerCount(){int n=0;for(Task t:tasks)if(t.h.loop!=Looper.MAIN)n++;return n;}
}

