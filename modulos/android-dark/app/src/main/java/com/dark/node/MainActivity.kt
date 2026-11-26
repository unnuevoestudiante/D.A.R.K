package com.dark.node

import android.Manifest
import android.content.Intent
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Close
import androidx.compose.material.icons.filled.Mic
import androidx.compose.material.icons.filled.Send
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dark.node.core.ActivationMode
import com.dark.node.core.DarkBackgroundService
import com.dark.node.core.DarkBus
import com.dark.node.core.DarkLauncher
import com.dark.node.overlay.OverlayService
import com.dark.node.ui.DarkColors
import com.dark.node.ui.DarkTheme

/**
 * Dos modos de pantalla:
 *
 *  1. CONFIG (por defecto): se ve cuando el usuario abre la app manualmente.
 *     Pide permisos, arranca el servicio y muestra instrucciones.
 *
 *  2. INPUT: se activa al recibir [EXTRA_INPUT_MODE]=true. Se abre
 *     automáticamente cuando el usuario mantiene presionado el botón de
 *     encendido (a través de [com.dark.node.core.DarkSessionService]).
 *     Muestra: micrófono, campo de texto, última respuesta.
 *
 * La comunicación con el servicio va por [DarkBus] (StateFlow en proceso).
 */
class MainActivity : ComponentActivity() {

    companion object {
        const val EXTRA_INPUT_MODE = "com.dark.node.INPUT_MODE"
    }

    private var inputMode by mutableStateOf(false)
    private var status by mutableStateOf("Iniciando Dark…")

    private val askPermissions =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { grants ->
            val allGranted = grants.values.all { it }
            status = if (allGranted) {
                "Permisos concedidos. Dark ya está activo."
            } else {
                "Algunos permisos fueron denegados. Dark puede funcionar con limitaciones."
            }
            startDarkService()
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        inputMode = intent?.getBooleanExtra(EXTRA_INPUT_MODE, false) == true

        if (!inputMode) {
            // Flujo de configuración normal (apertura manual).
            startDarkService()
            if (!OverlayService.canDraw(this)) {
                startActivity(
                    Intent(
                        Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        android.net.Uri.parse("package:$packageName"),
                    ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                )
            }
            requestPermissions()
        } else {
            // Flujo de input (botón de encendido largo).
            // No hace falta pedir permisos aquí — el servicio ya está corriendo.
            // Solo aseguramos que el servicio esté vivo.
            DarkLauncher.start(this, "app")
        }

        setContent {
            DarkTheme {
                if (inputMode) {
                    InputScreen(
                        onCerrar = { finish() },
                        onEnviarTexto = { texto -> enviarTextoAlServicio(texto) },
                        onPedirMicrofono = { pedirMicrofonoAlServicio() },
                    )
                } else {
                    ConfigScreen(status = status)
                }
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        // Si la activity ya estaba abierta y llega otro intent con inputMode,
        // pasamos a modo input sin recrear.
        if (intent.getBooleanExtra(EXTRA_INPUT_MODE, false)) {
            inputMode = true
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        // Avisar al servicio de que la interfaz se cerró. El servicio reanuda
        // el wake word si estaba corriendo antes.
        try {
            val i = Intent(this, DarkBackgroundService::class.java).apply {
                action = DarkBackgroundService.ACTION_STOP_LISTENING
            }
            startService(i)
        } catch (_: Exception) {}
    }

    // --------------------------------------------------------------- intents al servicio

    private fun startDarkService() {
        DarkLauncher.start(this, "app")
    }

    private fun requestPermissions() {
        val wanted = mutableListOf(
            Manifest.permission.RECORD_AUDIO,
            Manifest.permission.CALL_PHONE,
            Manifest.permission.READ_CONTACTS,
            Manifest.permission.CAMERA,
            Manifest.permission.ACCESS_FINE_LOCATION,
            Manifest.permission.ACCESS_COARSE_LOCATION,
        )
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            wanted += Manifest.permission.POST_NOTIFICATIONS
        }
        askPermissions.launch(wanted.toTypedArray())
    }

    private fun enviarTextoAlServicio(texto: String) {
        if (texto.isBlank()) return
        val i = Intent(this, DarkBackgroundService::class.java).apply {
            action = DarkBackgroundService.ACTION_PROCESS_TEXT
            putExtra(DarkBackgroundService.EXTRA_TEXT, texto)
        }
        startService(i)
    }

    private fun pedirMicrofonoAlServicio() {
        val i = Intent(this, DarkBackgroundService::class.java).apply {
            action = DarkBackgroundService.ACTION_START_LISTENING
        }
        startService(i)
    }
}

// ============================================================================
//   Pantalla de configuración (la que ya existía)
// ============================================================================

@Composable
private fun ConfigScreen(status: String) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkColors.GalaxyBrush),
        contentAlignment = Alignment.Center,
    ) {
        Column(
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center,
            modifier = Modifier.padding(40.dp),
        ) {
            Box(
                modifier = Modifier
                    .size(88.dp)
                    .clip(CircleShape)
                    .background(
                        Brush.radialGradient(
                            colors = listOf(
                                DarkColors.CyanBright,
                                DarkColors.Cyan,
                                DarkColors.CyanDim,
                                DarkColors.SpaceDeep,
                            )
                        )
                    )
            )

            Spacer(Modifier.height(28.dp))

            Text(
                text = "DARK",
                color = DarkColors.CyanBright,
                fontSize = 28.sp,
                fontWeight = FontWeight.Bold,
                letterSpacing = 8.sp,
            )

            Spacer(Modifier.height(8.dp))

            Text(
                text = "Nodo del teléfono",
                color = DarkColors.Muted,
                fontSize = 13.sp,
                letterSpacing = 2.sp,
            )

            Spacer(Modifier.height(40.dp))

            Text(
                text = status,
                color = DarkColors.TextSecondary,
                fontSize = 14.sp,
                textAlign = TextAlign.Center,
                lineHeight = 22.sp,
            )

            Spacer(Modifier.height(32.dp))

            Text(
                text = "Di \"Dark\", \"Módulo\" o \"Jarvis\" en cualquier momento.\n\n" +
                        "Para usar el botón de encendido:\n" +
                        "Ajustes → Apps → Asistente predeterminado → Dark",
                color = DarkColors.MutedDark,
                fontSize = 12.sp,
                textAlign = TextAlign.Center,
                lineHeight = 19.sp,
            )
        }
    }
}

// ============================================================================
//   Pantalla de input (nueva)
// ============================================================================

@Composable
private fun InputScreen(
    onCerrar: () -> Unit,
    onEnviarTexto: (String) -> Unit,
    onPedirMicrofono: () -> Unit,
) {
    val estado by DarkBus.estado.collectAsState()
    var textoEscrito by remember { mutableStateOf("") }
    val focusRequester = remember { FocusRequester() }

    // Enfocar el campo de texto al entrar.
    LaunchedEffect(Unit) {
        focusRequester.requestFocus()
    }

    // Cuando llega texto parcial por voz, sincronizarlo con el campo.
    LaunchedEffect(estado.textoUsuario) {
        if (estado.fase == DarkBus.Fase.Listening) {
            textoEscrito = estado.textoUsuario
        }
    }

    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(DarkColors.SpaceDeep)
            .padding(20.dp),
    ) {
        Column(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.SpaceBetween,
        ) {

            // ---------- cabecera con botón cerrar ----------
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(
                    text = "DARK",
                    color = DarkColors.Cyan,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Bold,
                    letterSpacing = 4.sp,
                )
                IconButton(onClick = onCerrar) {
                    Icon(
                        imageVector = Icons.Filled.Close,
                        contentDescription = "Cerrar",
                        tint = DarkColors.Muted,
                    )
                }
            }

            // ---------- cuerpo: respuesta + estado ----------
            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                // Estado actual (Listening / Thinking / Speaking / Idle / Error).
                Text(
                    text = when (estado.fase) {
                        DarkBus.Fase.Listening -> "Escuchando…"
                        DarkBus.Fase.Thinking -> "Pensando…"
                        DarkBus.Fase.Speaking -> "Respondiendo…"
                        DarkBus.Fase.Error -> "Error"
                        DarkBus.Fase.Idle -> ""
                    },
                    color = DarkColors.CyanDim,
                    fontSize = 12.sp,
                    letterSpacing = 2.sp,
                )

                Spacer(Modifier.height(16.dp))

                // Última respuesta de Dark.
                if (estado.ultimaRespuesta.isNotBlank()) {
                    Box(
                        modifier = Modifier
                            .fillMaxWidth()
                            .clip(RoundedCornerShape(14.dp))
                            .background(DarkColors.MicIdle)
                            .padding(18.dp),
                    ) {
                        Text(
                            text = estado.ultimaRespuesta,
                            color = DarkColors.TextPrimary,
                            fontSize = 15.sp,
                            lineHeight = 22.sp,
                        )
                    }
                } else {
                    Box(
                        modifier = Modifier
                            .size(60.dp)
                            .clip(CircleShape)
                            .background(
                                Brush.radialGradient(
                                    colors = listOf(
                                        DarkColors.Cyan,
                                        DarkColors.CyanDim,
                                        DarkColors.SpaceDeep,
                                    )
                                )
                            )
                    )
                }
            }

            // ---------- barra inferior: micrófono + texto + enviar ----------
            Row(
                modifier = Modifier.fillMaxWidth(),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                IconButton(
                    onClick = onPedirMicrofono,
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(
                            if (estado.fase == DarkBus.Fase.Listening)
                                DarkColors.Cyan
                            else
                                DarkColors.MicIdle
                        ),
                ) {
                    Icon(
                        imageVector = Icons.Filled.Mic,
                        contentDescription = "Hablar",
                        tint = if (estado.fase == DarkBus.Fase.Listening)
                            DarkColors.SpaceDeep
                        else
                            DarkColors.TextSecondary,
                    )
                }

                Spacer(Modifier.size(8.dp))

                OutlinedTextField(
                    value = textoEscrito,
                    onValueChange = { textoEscrito = it },
                    modifier = Modifier
                        .weight(1f)
                        .focusRequester(focusRequester),
                    placeholder = {
                        Text(
                            "Escribe o dicta algo…",
                            color = DarkColors.MutedDark,
                            fontSize = 14.sp,
                        )
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(24.dp),
                    colors = TextFieldDefaults.colors(
                        focusedContainerColor = DarkColors.MicIdle,
                        unfocusedContainerColor = DarkColors.MicIdle,
                        focusedIndicatorColor = DarkColors.Cyan,
                        unfocusedIndicatorColor = Color.Transparent,
                        focusedTextColor = DarkColors.TextPrimary,
                        unfocusedTextColor = DarkColors.TextPrimary,
                        cursorColor = DarkColors.Cyan,
                    ),
                )

                Spacer(Modifier.size(8.dp))

                IconButton(
                    onClick = {
                        val t = textoEscrito.trim()
                        if (t.isNotEmpty()) {
                            onEnviarTexto(t)
                            textoEscrito = ""
                        }
                    },
                    modifier = Modifier
                        .size(48.dp)
                        .clip(CircleShape)
                        .background(DarkColors.Cyan),
                ) {
                    Icon(
                        imageVector = Icons.Filled.Send,
                        contentDescription = "Enviar",
                        tint = DarkColors.SpaceDeep,
                    )
                }
            }
        }
    }
}