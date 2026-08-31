package android.content;
public class Context { public static final int MODE_PRIVATE=0; public boolean deviceProtected;
 public final SharedPreferences prefs=new SharedPreferences(); public Context getApplicationContext(){return this;}
 public Context createDeviceProtectedStorageContext(){deviceProtected=true;return this;}
 public SharedPreferences getSharedPreferences(String n,int m){return prefs;}
 public <T>T getSystemService(Class<T> cls){try{return cls.newInstance();}catch(Exception e){throw new RuntimeException(e);}}
}
