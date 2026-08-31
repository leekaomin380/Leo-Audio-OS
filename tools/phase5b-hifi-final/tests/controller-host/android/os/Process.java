package android.os; public class Process { public static boolean owner=true; public static UserHandle myUserHandle(){return owner?UserHandle.SYSTEM:new UserHandle();} }
