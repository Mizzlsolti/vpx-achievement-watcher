package com.vpxwatcher.app.data

import kotlinx.serialization.json.*

/**
 * GitHub Releases API check for in-app updates.
 */
class UpdateRepository {

    private val json = FirebaseClient.json

    companion object {
        private const val RELEASES_URL =
            "https://api.github.com/repos/Mizzlsolti/vpx-achievement-watcher/releases/latest"
    }

    /** Check latest release from GitHub. */
    suspend fun checkLatestRelease(): ReleaseInfo? {
        val raw = FirebaseClient.fetchUrl(RELEASES_URL) ?: return null
        return try {
            val obj = json.parseToJsonElement(raw)
            if (obj is JsonObject) {
                val tagName = obj["tag_name"]?.jsonPrimitive?.contentOrNull ?: return null
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

                ReleaseInfo(
                    tagName = tagName,
                    version = tagName.removePrefix("v").removePrefix("V"),
                    body = body,
                    htmlUrl = htmlUrl,
                    apkDownloadUrl = apkUrl,
                )
            } else null
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
