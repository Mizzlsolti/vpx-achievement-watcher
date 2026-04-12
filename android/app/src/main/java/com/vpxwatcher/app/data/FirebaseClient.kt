package com.vpxwatcher.app.data

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import java.io.IOException
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/**
 * Firebase Realtime Database REST client matching the Watcher's CloudSync approach.
 * Uses plain HTTP requests — no Firebase SDK.
 */
object FirebaseClient {
    private val client = OkHttpClient.Builder()
        .readTimeout(30, java.util.concurrent.TimeUnit.SECONDS)
        .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    private val sseClient = OkHttpClient.Builder()
        .readTimeout(0, java.util.concurrent.TimeUnit.MINUTES) // SSE = long-lived
        .connectTimeout(15, java.util.concurrent.TimeUnit.SECONDS)
        .build()

    val json = Json {
        ignoreUnknownKeys = true
        isLenient = true
        coerceInputValues = true
    }

    private fun buildUrl(baseUrl: String, path: String): String {
        val base = baseUrl.trimEnd('/')
        return "$base/$path.json"
    }

    /** GET a Firebase node. Returns the raw JSON string or null. */
    suspend fun getNode(baseUrl: String, path: String): String? = withContext(Dispatchers.IO) {
        val url = buildUrl(baseUrl, path)
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .get()
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(null)
                }
                override fun onResponse(call: Call, response: Response) {
                    val body = response.body?.string()
                    if (cont.isActive) cont.resume(body)
                }
            })
        }
    }

    /** GET a Firebase node with shallow=true. Returns the raw JSON string or null. */
    suspend fun getNodeShallow(baseUrl: String, path: String): String? = withContext(Dispatchers.IO) {
        val base = baseUrl.trimEnd('/')
        val url = "$base/$path.json?shallow=true"
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .get()
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(null)
                }
                override fun onResponse(call: Call, response: Response) {
                    val body = response.body?.string()
                    if (cont.isActive) cont.resume(body)
                }
            })
        }
    }

    /** PUT (set) a Firebase node. */
    suspend fun setNode(baseUrl: String, path: String, data: String): Boolean = withContext(Dispatchers.IO) {
        val url = buildUrl(baseUrl, path)
        val body = data.toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .put(body)
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(false)
                }
                override fun onResponse(call: Call, response: Response) {
                    response.close()
                    if (cont.isActive) cont.resume(response.isSuccessful)
                }
            })
        }
    }

    /** PATCH (update) a Firebase node. */
    suspend fun patchNode(baseUrl: String, path: String, data: String): Boolean = withContext(Dispatchers.IO) {
        val url = buildUrl(baseUrl, path)
        val body = data.toRequestBody("application/json".toMediaType())
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .patch(body)
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(false)
                }
                override fun onResponse(call: Call, response: Response) {
                    response.close()
                    if (cont.isActive) cont.resume(response.isSuccessful)
                }
            })
        }
    }

    /** DELETE a Firebase node. */
    suspend fun deleteNode(baseUrl: String, path: String): Boolean = withContext(Dispatchers.IO) {
        val url = buildUrl(baseUrl, path)
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .delete()
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(false)
                }
                override fun onResponse(call: Call, response: Response) {
                    response.close()
                    if (cont.isActive) cont.resume(response.isSuccessful)
                }
            })
        }
    }

    /** Fetch a raw URL (non-Firebase). Returns the body string or null. */
    suspend fun fetchUrl(url: String): String? = withContext(Dispatchers.IO) {
        val request = Request.Builder()
            .url(url)
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .get()
            .build()
        suspendCancellableCoroutine { cont ->
            val call = client.newCall(request)
            cont.invokeOnCancellation { call.cancel() }
            call.enqueue(object : Callback {
                override fun onFailure(call: Call, e: IOException) {
                    if (cont.isActive) cont.resume(null)
                }
                override fun onResponse(call: Call, response: Response) {
                    val body = response.body?.string()
                    if (cont.isActive) cont.resume(body)
                }
            })
        }
    }

    /**
     * Open an SSE (Server-Sent Events) stream to a Firebase path.
     * Calls [onEvent] with event type and data for each SSE event.
     * Returns the EventSource which can be cancelled.
     */
    fun openSseStream(
        baseUrl: String,
        path: String,
        onEvent: (eventType: String, data: String) -> Unit,
        onFailure: (Throwable) -> Unit = {}
    ): EventSource {
        val base = baseUrl.trimEnd('/')
        val url = "$base/$path.json"
        val request = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .header("User-Agent", "VpxWatcherAndroid/1.0")
            .header("Cache-Control", "no-cache")
            .build()

        val listener = object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                if (type != null && data.isNotEmpty()) {
                    onEvent(type, data)
                }
            }
            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                if (t != null) onFailure(t)
            }
        }

        return EventSources.createFactory(sseClient).newEventSource(request, listener)
    }
}
