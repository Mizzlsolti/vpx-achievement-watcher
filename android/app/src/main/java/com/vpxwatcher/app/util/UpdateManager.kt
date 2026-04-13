package com.vpxwatcher.app.util

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Environment
import androidx.core.content.FileProvider
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.net.URL

/**
 * GitHub release check + APK download/install via FileProvider.
 */
object UpdateManager {

    /**
     * Download APK from URL and trigger install intent.
     * Uses FileProvider for Android 7+ compatibility.
     */
    suspend fun downloadAndInstall(context: Context, apkUrl: String): Boolean {
        return withContext(Dispatchers.IO) {
            try {
                val updatesDir = File(context.getExternalFilesDir(null), "updates")
                if (!updatesDir.exists()) updatesDir.mkdirs()

                val apkFile = File(updatesDir, "vpx-watcher-update.apk")
                if (apkFile.exists()) apkFile.delete()

                // Download
                val connection = URL(apkUrl).openConnection()
                connection.connect()
                val input = connection.getInputStream()
                val output = FileOutputStream(apkFile)
                input.copyTo(output)
                output.close()
                input.close()

                // Install via FileProvider
                val uri = FileProvider.getUriForFile(
                    context,
                    "${context.packageName}.fileprovider",
                    apkFile
                )

                val installIntent = Intent(Intent.ACTION_VIEW).apply {
                    setDataAndType(uri, "application/vnd.android.package-archive")
                    flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_GRANT_READ_URI_PERMISSION
                }
                context.startActivity(installIntent)
                true
            } catch (e: Exception) {
                false
            }
        }
    }
}
