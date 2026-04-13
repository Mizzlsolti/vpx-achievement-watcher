package com.vpxwatcher.app.data

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow
import kotlinx.coroutines.flow.flowOn
import kotlinx.coroutines.isActive
import okhttp3.OkHttpClient
import okhttp3.Request
import java.io.BufferedInputStream
import java.io.ByteArrayOutputStream
import java.util.concurrent.TimeUnit
import kotlin.coroutines.coroutineContext

/**
 * Parses an MJPEG multipart/x-mixed-replace HTTP stream and emits decoded
 * [Bitmap] frames as a [Flow].
 *
 * The parser is byte-oriented so it handles any boundary string the server
 * uses.  Each JPEG frame is decoded on the IO dispatcher.
 */
class MjpegClient {

    private val client = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS)   // no read timeout — streaming
        .build()

    /**
     * Opens the MJPEG stream at [url] and emits each JPEG frame as a [Bitmap].
     * The flow completes when the stream ends or an unrecoverable error occurs.
     */
    fun stream(url: String): Flow<Bitmap> = flow {
        val request = Request.Builder().url(url).build()
        val response = client.newCall(request).execute()
        if (!response.isSuccessful) {
            response.close()
            return@flow
        }
        val body = response.body ?: run { response.close(); return@flow }
        val inputStream = BufferedInputStream(body.byteStream(), 65536)

        try {
            while (coroutineContext.isActive) {
                // Read until we find the start-of-JPEG magic bytes (FF D8).
                val jpeg = readNextJpeg(inputStream) ?: break
                val bitmap = BitmapFactory.decodeByteArray(jpeg, 0, jpeg.size) ?: continue
                emit(bitmap)
            }
        } finally {
            try { inputStream.close() } catch (_: Exception) {}
            try { response.close() } catch (_: Exception) {}
        }
    }.flowOn(Dispatchers.IO)

    /**
     * Scans the stream for the next JPEG frame by looking for the SOI marker
     * (0xFF 0xD8) and reads until the EOI marker (0xFF 0xD9).
     *
     * Returns null when the stream is exhausted.
     */
    private fun readNextJpeg(stream: BufferedInputStream): ByteArray? {
        // Find SOI
        var prev = -1
        while (true) {
            val b = stream.read()
            if (b == -1) return null
            if (prev == 0xFF && b == 0xD8) break
            prev = b
        }

        // We have found 0xFF 0xD8 — collect bytes until we see 0xFF 0xD9
        val buf = ByteArrayOutputStream(32768)
        buf.write(0xFF)
        buf.write(0xD8)

        var p = -1
        while (true) {
            val b = stream.read()
            if (b == -1) return null
            buf.write(b)
            if (p == 0xFF && b == 0xD9) break   // EOI
            p = b
        }
        return buf.toByteArray()
    }
}
