package com.vpxwatcher.app.data

import android.graphics.Bitmap
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.withContext
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

@Serializable
data class MonitorInfo(
    val id: Int,
    val x: Int,
    val y: Int,
    val w: Int,
    val h: Int,
    val name: String,
)

@Serializable
data class MonitorsResponse(
    val monitors: List<MonitorInfo>,
    val hostname: String = "",
)

/**
 * Data-layer access to the desktop VPX Watcher screen-capture server.
 *
 * - [fetchMonitors] queries /api/monitors and returns the list of physical
 *   monitors with their real screen coordinates (position + size), exactly
 *   as Windows reports them.
 * - [createMjpegStream] returns a [Flow] of [Bitmap] frames for a given
 *   monitor id.
 */
class ScreenCaptureRepository {

    private val http = OkHttpClient.Builder()
        .connectTimeout(5, TimeUnit.SECONDS)
        .readTimeout(5, TimeUnit.SECONDS)
        .build()

    private val json = Json { ignoreUnknownKeys = true }

    private val mjpegClient = MjpegClient()

    /** Fetch the list of monitors from the desktop watcher server. */
    suspend fun fetchMonitors(baseUrl: String): Result<MonitorsResponse> =
        withContext(Dispatchers.IO) {
            try {
                val url = baseUrl.trimEnd('/') + "/api/monitors"
                val request = Request.Builder().url(url).build()
                val response = http.newCall(request).execute()
                val body = response.body?.string() ?: return@withContext Result.failure(
                    IllegalStateException("Empty response")
                )
                response.close()
                if (!response.isSuccessful) {
                    return@withContext Result.failure(
                        IllegalStateException("HTTP ${response.code}")
                    )
                }
                val parsed = json.decodeFromString<MonitorsResponse>(body)
                Result.success(parsed)
            } catch (e: Exception) {
                Result.failure(e)
            }
        }

    /** Returns a cold [Flow] of JPEG frames for [monitorId] from [baseUrl]. */
    fun createMjpegStream(baseUrl: String, monitorId: Int): Flow<Bitmap> {
        val url = baseUrl.trimEnd('/') + "/stream/$monitorId"
        return mjpegClient.stream(url)
    }
}
