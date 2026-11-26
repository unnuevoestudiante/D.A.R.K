package com.dark.node.overlay

import android.app.Service
import android.content.Context
import android.content.Intent
import android.graphics.PixelFormat
import android.os.IBinder
import android.provider.Settings
import android.util.Log
import android.view.Gravity
import android.view.WindowManager
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.runtime.mutableStateOf
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.ComposeView
import androidx.compose.ui.unit.dp
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelStoreOwner
import androidx.lifecycle.setViewTreeLifecycleOwner
import androidx.lifecycle.setViewTreeViewModelStoreOwner
import androidx.savedstate.SavedStateRegistry
import androidx.savedstate.SavedStateRegistryController
import androidx.savedstate.SavedStateRegistryOwner
import androidx.savedstate.setViewTreeSavedStateRegistryOwner
import com.dark.node.core.DarkSnapshot
import com.dark.node.core.DarkState
import com.dark.node.ui.DarkOverlay
import com.dark.node.ui.DarkTheme

/**
 * Capa de Dark encima de cualquier app. Vive dentro del proceso del servicio de fondo
 * (que ya es de primer plano), así que no necesita notificación propia.
 * Necesita el permiso "mostrar sobre otras apps".
 */
class OverlayService : Service(), LifecycleOwner, ViewModelStoreOwner, SavedStateRegistryOwner {

    companion object {
        private val current = mutableStateOf(DarkSnapshot())

        /** Nombre del módulo mientras está enlazado con Núcleo; null si no hay enlace. */
        private val linkName = mutableStateOf<String?>(null)

        @Volatile
        private var running = false

        fun canDraw(context: Context): Boolean = Settings.canDrawOverlays(context)

        fun setLink(name: String?) {
            linkName.value = name
        }

        /** Actualiza lo que se dibuja y arranca la capa si todavía no existe. */
        fun update(context: Context, snapshot: DarkSnapshot) {
            current.value = snapshot
            if (!running && canDraw(context)) {
                context.startService(Intent(context, OverlayService::class.java))
            }
        }
    }

    private val registry = LifecycleRegistry(this)
    private val savedState = SavedStateRegistryController.create(this)
    private val store = ViewModelStore()

    override val lifecycle: Lifecycle get() = registry
    override val viewModelStore: ViewModelStore get() = store
    override val savedStateRegistry: SavedStateRegistry get() = savedState.savedStateRegistry

    private var view: ComposeView? = null

    override fun onCreate() {
        super.onCreate()
        savedState.performRestore(null)
        registry.currentState = Lifecycle.State.CREATED
        if (!attachOverlay()) {
            stopSelf()
            return
        }
        running = true
        registry.currentState = Lifecycle.State.RESUMED
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_NOT_STICKY

    private fun attachOverlay(): Boolean {
        if (!canDraw(this)) {
            Log.w("Dark", "Overlay: falta el permiso 'mostrar sobre otras apps'")
            return false
        }

        val wm = getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY,
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                    WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                    WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN or
                    WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT,
        ).apply { gravity = Gravity.CENTER }

        val composeView = ComposeView(this).apply {
            setViewTreeLifecycleOwner(this@OverlayService)
            setViewTreeViewModelStoreOwner(this@OverlayService)
            setViewTreeSavedStateRegistryOwner(this@OverlayService)
            setContent {
                DarkTheme {
                    // Centrar TODO el overlay en la pantalla
                    Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) {
                        val name = linkName.value
                        DarkOverlay(
                            snapshot = current.value,
                            linked = name != null,
                            linkLabel = name?.let { "$it · Colmena" },
                            modifier = Modifier.align(Alignment.Center),
                        )
                    }
                }
            }
        }

        return try {
            wm.addView(composeView, params)
            view = composeView
            Log.i("Dark", "Overlay creado")
            true
        } catch (e: Exception) {
            Log.e("Dark", "Overlay: no se pudo añadir la ventana: ${e.javaClass.simpleName}")
            false
        }
    }

    override fun onDestroy() {
        running = false
        view?.let { v ->
            runCatching {
                (getSystemService(Context.WINDOW_SERVICE) as WindowManager).removeView(v)
            }
        }
        view = null
        registry.currentState = Lifecycle.State.DESTROYED
        super.onDestroy()
    }

    override fun onBind(intent: Intent?): IBinder? = null
}