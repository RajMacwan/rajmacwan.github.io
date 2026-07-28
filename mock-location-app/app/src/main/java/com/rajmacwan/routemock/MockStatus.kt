package com.rajmacwan.routemock

import android.app.AppOpsManager
import android.content.Context
import android.os.Build
import android.os.Process

/** Whether this app is the one chosen under Developer Options → "Select mock location app". */
object MockStatus {

    // The op constant AppOpsManager.OPSTR_MOCK_LOCATION is @hide, but the string value
    // is a stable public contract. Selecting the app in Developer Options flips this op
    // to MODE_ALLOWED for exactly that package — the same source of truth the framework uses.
    private const val OP_MOCK_LOCATION = "android:mock_location"

    /** True iff this app is the selected mock-location app. Pure read, no side effects. */
    fun isSelectedMockApp(context: Context): Boolean {
        val appOps = context.getSystemService(Context.APP_OPS_SERVICE) as? AppOpsManager
            ?: return false
        val mode = try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                appOps.unsafeCheckOpNoThrow(OP_MOCK_LOCATION, Process.myUid(), context.packageName)
            } else {
                @Suppress("DEPRECATION")
                appOps.checkOpNoThrow(OP_MOCK_LOCATION, Process.myUid(), context.packageName)
            }
        } catch (e: Throwable) {
            return false
        }
        return mode == AppOpsManager.MODE_ALLOWED
    }
}
