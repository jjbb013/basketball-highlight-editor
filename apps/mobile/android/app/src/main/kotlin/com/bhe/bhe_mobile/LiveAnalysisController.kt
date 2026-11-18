package com.bhe.bhe_mobile

import android.content.Context
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Handler
import android.os.HandlerThread
import android.util.Log
import io.flutter.plugin.common.EventChannel
import io.flutter.plugin.common.MethodCall
import io.flutter.plugin.common.MethodChannel
import java.nio.ByteBuffer
import java.util.concurrent.atomic.AtomicBoolean
import org.json.JSONObject

/**
 * Real-time (live capture) analysis controller.
 *
 * Reuses the existing Rust JNI session API (NativeRuntime.createSession +
 * pushFrameYuv) in coarse_mode so the crossing/candidate logic in
 * packages/bhe_runtime runs unchanged on live camera frames. Frames arrive
 * from Flutter's camera plugin image stream as YUV_420_888 planes and are
 * forwarded to the native runtime on a dedicated background thread so the
 * platform thread is never blocked by inference.
 *
 * Goal candidates emitted by the runtime are deduplicated with a short
 * debounce and forwarded to Flutter through the live analysis event channel.
 * A short tone is played natively so no audio asset is required.
 */
class LiveAnalysisController(private val context: Context) {

    companion object {
        private const val TAG = "BHE-LiveAnalysis"
        private const val COARSE_MODEL_SIZE = 640
        private const val COARSE_MAX_DIMENSION = 960
        private const val GOAL_DEBOUNCE_MS = 800L
        private const val LIVE_SESSION_DURATION_MS = 24L * 3600 * 1000
        private val mainHandler = Handler(android.os.Looper.getMainLooper())
    }

    @Volatile
    var eventSink: EventChannel.EventSink? = null
        private set

    private val lock = Any()
    private var session: Long = 0
    private var worker: HandlerThread? = null
    private var workerHandler: Handler? = null
    private var lastGoalEmittedAtMs = 0L
    private var goalCount = 0
    private var frameCount = 0L
    private var droppedFrames = 0L
    private val busy = AtomicBoolean(false)

    fun attachSink(sink: EventChannel.EventSink?) {
        eventSink = sink
    }

    fun start(call: MethodCall, result: MethodChannel.Result) {
        val modelPath = call.argument<String>("modelPath")
        if (modelPath.isNullOrEmpty()) {
            result.error("invalid_args", "modelPath is required", null)
            return
        }
        val nativeLibraryDir = context.applicationInfo.nativeLibraryDir
        val onnxPath = java.io.File(nativeLibraryDir, "libonnxruntime.so").absolutePath
        if (!NativeRuntime.ensureLoaded(nativeLibraryDir)) {
            result.error("native_unavailable", NativeRuntime.loadError ?: "runtime load failed", null)
            return
        }
        if (!NativeRuntime.ensureOnnxLoaded(onnxPath)) {
            result.error("onnx_unavailable", "ONNX runtime load failed: $onnxPath", null)
            return
        }
        if (!NativeRuntime.initializeOnnx(onnxPath)) {
            result.error("onnx_init", "initializeOnnx returned false", null)
            return
        }
        val executionProvider = call.argument<String>("executionProvider") ?: "cpu"
        if (executionProvider == "qnn") {
            // QNN HTP needs the DSP library path exported before session
            // creation, matching InferenceTuner's setup.
            try {
                android.system.Os.setenv(
                    "ADSP_LIBRARY_PATH",
                    context.applicationInfo.nativeLibraryDir,
                    true,
                )
            } catch (t: Throwable) {
                Log.w(TAG, "ADSP_LIBRARY_PATH export failed", t)
            }
        }
        synchronized(lock) {
            if (session != 0L) {
                NativeRuntime.freeSession(session)
                session = 0
            }
            val analysisRoi = call.argument<Map<String, Any>>("analysisRoi")
            val rim = call.argument<Map<String, Any>>("rim")
            val confidence = (call.argument<Double>("confidence") ?: 0.10).toFloat()
            val intraThreads = call.argument<Int>("intraThreads") ?: 4

            val config = JSONObject()
                .put("model_path", modelPath)
                .put("hoop_roi", rim?.let(::roiJson) ?: fullRoi())
                .put("analysis_roi", analysisRoi?.let(::roiJson) ?: fullRoi())
                .put("net_roi", fullRoi())
                .put("duration_ms", LIVE_SESSION_DURATION_MS)
                .put("confidence_threshold", confidence.toDouble())
                .put("model_size", COARSE_MODEL_SIZE)
                .put("crop_scale", 4.0)
                .put("input_max_dimension", COARSE_MAX_DIMENSION)
                .put("detection_only", false)
                .put("coarse_mode", true)
                .put("intra_threads", intraThreads)
                .put("execution_provider", executionProvider)
                .put("inference_batch_size", 1)
            val handle = NativeRuntime.createSession(config.toString())
            if (handle == 0L) {
                result.error(
                    "session_create_failed",
                    NativeRuntime.sessionCreateError(),
                    null,
                )
                return@synchronized
            }
            session = handle
            goalCount = 0
            frameCount = 0
            droppedFrames = 0
            lastGoalEmittedAtMs = 0
            Log.i(TAG, "live session created: ${NativeRuntime.sessionInfo(handle)} provider=$executionProvider conf=$confidence")
        }
        ensureWorker()
        result.success(
            mapOf(
                "sessionInfo" to NativeRuntime.sessionInfo(session),
                "goals" to goalCount,
            ),
        )
    }

    fun pushFrame(call: MethodCall, result: MethodChannel.Result) {
        val handle: Long
        synchronized(lock) {
            handle = session
        }
        if (handle == 0L) {
            result.error("no_session", "live analysis session is not running", null)
            return
        }
        if (!busy.compareAndSet(false, true)) {
            // Inference is still busy with the previous frame; drop this one
            // so recording/analysis concurrency stays smooth on mid-range
            // devices. The next image-stream tick will pick analysis up.
            droppedFrames += 1
            result.success(mapOf("queued" to false, "dropped" to droppedFrames))
            return
        }
        val args = call.arguments<Map<String, Any?>>()
        val timeMs = (args?.get("timeMs") as? Number)?.toLong() ?: 0L
        val width = (args["width"] as? Number)?.toInt() ?: 0
        val height = (args["height"] as? Number)?.toInt() ?: 0
        val rotation = (args["rotationDegrees"] as? Number)?.toInt() ?: 0
        if (width <= 0 || height <= 0) {
            busy.set(false)
            result.error("invalid_frame", "YUV plane data is missing or dimensions are invalid", null)
            return
        }
        val planeArgs = fun(name: String): PlaneArgs {
            val m = args[name] as? Map<String, Any?> ?: emptyMap()
            return PlaneArgs(
                bytes = (m["bytes"] as? ByteArray) ?: ByteArray(0),
                rowStride = (m["rowStride"] as? Number)?.toInt() ?: 0,
                pixelStride = (m["pixelStride"] as? Number)?.toInt() ?: 1,
                offset = (m["offset"] as? Number)?.toInt() ?: 0,
            )
        }
        val y = planeArgs("y")
        val u = planeArgs("u")
        val v = planeArgs("v")
        val handler = workerHandler
        if (handler == null) {
            busy.set(false)
            result.error("no_worker", "analysis worker thread is not running", null)
            return
        }
        handler.post {
            var responseJson: JSONObject? = null
            var error: String? = null
            try {
                val response = NativeRuntime.pushFrameYuv(
                    handle, timeMs, width, height,
                    ByteBuffer.wrap(y.bytes), y.offset, y.bytes.size - y.offset, y.rowStride, y.pixelStride,
                    ByteBuffer.wrap(u.bytes), u.offset, u.bytes.size - u.offset, u.rowStride, u.pixelStride,
                    ByteBuffer.wrap(v.bytes), v.offset, v.bytes.size - v.offset, v.rowStride, v.pixelStride,
                    rotation,
                )
                responseJson = JSONObject(response)
                frameCount += 1
            } catch (t: Throwable) {
                Log.e(TAG, "pushFrameYuv failed", t)
                error = t.message ?: t.toString()
            } finally {
                busy.set(false)
            }
            val candidates = responseJson?.optJSONArray("candidates")
            if (candidates != null && candidates.length() > 0) {
                for (index in 0 until candidates.length()) {
                    val candidate = candidates.optJSONObject(index) ?: continue
                    val eventMs = candidate.optLong("event_ms", Long.MIN_VALUE)
                    if (eventMs == Long.MIN_VALUE) continue
                    emitGoal(candidate, eventMs)
                }
            }
            // Report back on the main thread result.
            mainHandler.post {
                if (error != null) {
                    result.error("push_failed", error, null)
                } else {
                    result.success(
                        mapOf(
                            "queued" to true,
                            "frameCount" to frameCount,
                            "dropped" to droppedFrames,
                            "detectionCount" to (responseJson?.optJSONArray("detections")?.length() ?: 0),
                        ),
                    )
                }
            }
        }
    }

    private fun emitGoal(candidate: JSONObject, eventMs: Long) {
        val now = System.currentTimeMillis()
        if (now - lastGoalEmittedAtMs < GOAL_DEBOUNCE_MS) return
        lastGoalEmittedAtMs = now
        goalCount += 1
        playGoalTone()
        val sink = eventSink
        mainHandler.post {
            sink?.success(
                mapOf(
                    "type" to "goal",
                    "eventMs" to eventMs,
                    "goals" to goalCount,
                    "confidence" to candidate.optDouble("confidence", 0.0),
                    "compositeScore" to candidate.optDouble("composite_score", 0.0),
                    "needsPostReview" to true,
                ),
            )
        }
    }

    fun playGoalTone() {
        try {
            val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 90)
            tone.startTone(ToneGenerator.TONE_PROP_ACK, 350)
            mainHandler.postDelayed({ tone.release() }, 600)
        } catch (t: Throwable) {
            Log.w(TAG, "goal tone failed", t)
        }
    }

    fun stop(result: MethodChannel.Result?) {
        val handle: Long
        synchronized(lock) {
            handle = session
            session = 0
        }
        val summary = JSONObject()
        if (handle != 0L) {
            try {
                val finished = NativeRuntime.finishSession(handle)
                summary.put("finished", JSONObject(finished).toString())
            } catch (t: Throwable) {
                Log.w(TAG, "finishSession failed", t)
                summary.put("finishError", t.message ?: t.toString())
            }
            try {
                NativeRuntime.freeSession(handle)
            } catch (t: Throwable) {
                Log.w(TAG, "freeSession failed", t)
            }
        }
        summary.put("goals", goalCount)
        summary.put("frames", frameCount)
        summary.put("dropped", droppedFrames)
        result?.success(summary.toString())
    }

    fun dispose() {
        stop(null)
        synchronized(lock) {
            worker?.quitSafely()
            worker = null
            workerHandler = null
        }
    }

    private fun ensureWorker() {
        synchronized(lock) {
            if (worker != null) return
            val thread = HandlerThread("bhe-live-analysis").also { it.start() }
            worker = thread
            workerHandler = Handler(thread.looper)
        }
    }

    private fun roiJson(map: Map<String, Any>): JSONObject = JSONObject()
        .put("left", (map["left"] as? Number)?.toDouble() ?: 0.0)
        .put("top", (map["top"] as? Number)?.toDouble() ?: 0.0)
        .put("right", (map["right"] as? Number)?.toDouble() ?: 1.0)
        .put("bottom", (map["bottom"] as? Number)?.toDouble() ?: 1.0)

    private fun fullRoi(): JSONObject = JSONObject()
        .put("left", 0.0)
        .put("top", 0.0)
        .put("right", 1.0)
        .put("bottom", 1.0)

    private data class PlaneArgs(
        val bytes: ByteArray,
        val rowStride: Int,
        val pixelStride: Int,
        val offset: Int,
    )
}
