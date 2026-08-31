package android.content;
public class SharedPreferences { public boolean saved; public int writes;
 public boolean getBoolean(String k,boolean def){return saved;}
 public Editor edit(){return new Editor();} public class Editor { boolean next; public Editor putBoolean(String k,boolean v){next=v;return this;} public void apply(){saved=next;writes++;} }
}
