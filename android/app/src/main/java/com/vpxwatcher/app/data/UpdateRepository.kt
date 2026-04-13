package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * GitHub Releases API check for in-app updates.
 * Filters for app-specific releases (tag_name starts with "app-v") so that
 * desktop Watcher releases (e.g. v3.0) are not shown to the user.
 */
class UpdateRepository {

    private val json = FirebaseClient.json

    companion object {
        private const val RELEASES_URL =
            "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases"
        private const val APP_TAG_PREFIX = "app-v"
    }

    /** Check latest app-specific release from GitHub. */
    suspend fun checkLatestRelease(): ReleaseInfo? {
        val raw = FirebaseClient.fetchUrl(RELEASES_URL) ?: return null
        return try {
            val arr = json.parseToJsonElement(raw)
            if (arr !is JsonArray) return null

            // Find the first (latest) release whose tag_name starts with "app-v"
            for (element in arr) {
                val obj = element as? JsonObject ?: continue
                val tagName = obj["tag_name"]?.jsonPrimitive?.contentOrNull ?: continue
                if (!tagName.startsWith(APP_TAG_PREFIX, ignoreCase = true)) continue

                val body = obj["body"]?.jsonPrimitive?.contentOrNull ?: ""
                val htmlUrl = obj["html_url"]?.jsonPrimitive?.contentOrNull ?: ""

                // Find APK asset
                val assets = obj["assets"]?.jsonArray
                val apkAsset = assets?.firstOrNull { asset ->
                    val name = (asset as? JsonObject)?.get("name")?.jsonPrimitive?.contentOrNull ?: ""
                    name.endsWith(".apk")
                }
                val apkUrl = (apkAsset as? JsonObject)?.get("browser_download_url")
                    ?.jsonPrimitive?.contentOrNull

                return ReleaseInfo(
                    tagName = tagName,
                    version = tagName.removePrefix("app-v").removePrefix("app-V"),
                    body = body,
                    htmlUrl = htmlUrl,
                    apkDownloadUrl = apkUrl,
                )
            }
            null // No app-v* release found
        } catch (_: Exception) { null }
    }
}

data class ReleaseInfo(
    val tagName: String,
    val version: String,
    val body: String,
    val htmlUrl: String,
    val apkDownloadUrl: String?,
)
