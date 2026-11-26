"""Ejecución de operaciones de terminal construidas desde una lista blanca."""

import base64
import os
import re
import subprocess
import sys
import threading

from nucleo.confirmacion import AlmacenConfirmacion


_RAIZ_PROYECTO = os.path.realpath(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
)
_OPERADORES_BLOQUEADOS = re.compile(r"[>|;]|&&|[\r\n`$]")
_PAQUETE_PYPI = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}(?:==[A-Za-z0-9.*+_-]+)?$"
)
_PAQUETE_NPM = re.compile(
    r"^(?:@[A-Za-z0-9._-]+/)?[A-Za-z0-9][A-Za-z0-9._-]{0,127}"
    r"(?:@[A-Za-z0-9.*+_-]+)?$"
)
_MODOS = frozenset(("asistente", "coder"))
_OPERACIONES_AMARILLAS = frozenset((
    "instalar_dependencia", "crear_directorio", "ejecutar_tests",
))


# Solo se admiten operaciones con argumentos validados y comandos fijos.
OPERACIONES_PERMITIDAS = {
    "listar_procesos": {
        "semaforo": "verde", "modos": _MODOS,
        "argumentos": {"nombre"},
    },
    "estado_git": {
        "semaforo": "verde", "modos": frozenset(("coder",)),
        "argumentos": {"ruta"},
    },
    "listar_directorio": {
        "semaforo": "verde", "modos": frozenset(("coder",)),
        "argumentos": {"ruta"},
    },
    "diagnostico_red": {
        "semaforo": "verde", "modos": _MODOS,
        "argumentos": set(),
    },
    "espacio_disco": {
        "semaforo": "verde", "modos": _MODOS,
        "argumentos": set(),
    },
    "instalar_dependencia": {
        "semaforo": "amarillo", "modos": frozenset(("coder",)),
        "argumentos": {"gestor", "paquete"},
    },
    "crear_directorio": {
        "semaforo": "amarillo", "modos": frozenset(("coder",)),
        "argumentos": {"ruta"},
    },
    "ejecutar_tests": {
        "semaforo": "amarillo", "modos": frozenset(("coder",)),
        "argumentos": {"tipo", "ruta"},
    },
}


class DarkTerminal:
    """Valida, confirma y ejecuta operaciones seguras de terminal."""

    def __init__(self, resumir_cb=None, raiz_workspace=None,
                 almacen_confirmaciones=None):
        self._resumir_cb = resumir_cb
        self._raiz = os.path.realpath(raiz_workspace or _RAIZ_PROYECTO)
        self._pendiente = None
        self._lock = threading.Lock()
        self._almacen_confirmaciones = (
            almacen_confirmaciones or AlmacenConfirmacion())

    @staticmethod
    def _literal_powershell(valor):
        """Escapa un valor dentro de un literal de texto de PowerShell."""
        return "'" + str(valor).replace("'", "''") + "'"

    @staticmethod
    def _bloqueo(mensaje):
        """Devuelve un rechazo identificable por el Núcleo y la capa de voz."""
        return {
            "ok": False,
            "codigo": "operacion_bloqueada",
            "mensaje": mensaje,
        }

    @staticmethod
    def _contiene_operador(valor):
        if isinstance(valor, str):
            return bool(_OPERADORES_BLOQUEADOS.search(valor))
        if isinstance(valor, dict):
            return any(DarkTerminal._contiene_operador(k)
                       or DarkTerminal._contiene_operador(v)
                       for k, v in valor.items())
        if isinstance(valor, (list, tuple)):
            return any(DarkTerminal._contiene_operador(v) for v in valor)
        return False

    def _resolver_ruta_workspace(self, ruta):
        if not isinstance(ruta, str) or not ruta.strip():
            raise ValueError("Indique una ruta dentro del workspace.")
        candidata = ruta.strip()
        if self._contiene_operador(candidata):
            raise ValueError("La ruta contiene operadores bloqueados.")
        if not os.path.isabs(candidata):
            candidata = os.path.join(self._raiz, candidata)
        resuelta = os.path.realpath(os.path.abspath(candidata))
        try:
            comun = os.path.commonpath((self._raiz, resuelta))
            if os.path.normcase(comun) != os.path.normcase(self._raiz):
                raise ValueError("La ruta debe permanecer dentro del workspace.")
        except ValueError as error:
            if "dentro del workspace" in str(error):
                raise
            raise ValueError("La ruta debe permanecer dentro del workspace.")
        return resuelta

    def _crear_comando(self, operacion, args):
        if operacion == "listar_procesos":
            nombre = args.get("nombre")
            if nombre is None:
                return ("Get-Process | Sort-Object -Property WS -Descending | "
                        "Select-Object -First 10 ProcessName,Id,CPU,WS")
            if not isinstance(nombre, str) or not re.fullmatch(
                    r"[A-Za-z0-9_.-]{1,80}", nombre):
                raise ValueError("El nombre del proceso no es válido.")
            return f"Get-Process -Name {self._literal_powershell(nombre)}"
        if operacion == "estado_git":
            ruta = self._resolver_ruta_workspace(args.get("ruta", "."))
            return (f"git -C {self._literal_powershell(ruta)} "
                    "status --short")
        if operacion == "listar_directorio":
            ruta = self._resolver_ruta_workspace(args.get("ruta", "."))
            return (f"Get-ChildItem -LiteralPath "
                    f"{self._literal_powershell(ruta)} -Name")
        if operacion == "diagnostico_red":
            return "Get-NetIPConfiguration"
        if operacion == "espacio_disco":
            return "Get-PSDrive -PSProvider FileSystem"
        if operacion == "instalar_dependencia":
            gestor = args.get("gestor")
            paquete = args.get("paquete")
            if gestor == "pip" and isinstance(paquete, str) and _PAQUETE_PYPI.fullmatch(paquete):
                ejecutable = self._literal_powershell(sys.executable)
                return (f"& {ejecutable} -m pip install "
                        f"{self._literal_powershell(paquete)}")
            if gestor == "npm" and isinstance(paquete, str) and _PAQUETE_NPM.fullmatch(paquete):
                return f"npm.cmd install {self._literal_powershell(paquete)}"
            raise ValueError("Gestor o identificador de paquete no válido.")
        if operacion == "crear_directorio":
            ruta = self._resolver_ruta_workspace(args.get("ruta"))
            return ("New-Item -ItemType Directory -Force -Path "
                    f"{self._literal_powershell(ruta)}")
        if operacion == "ejecutar_tests":
            tipo = args.get("tipo", "pytest")
            if tipo == "pytest":
                ejecutable = self._literal_powershell(sys.executable)
                return f"& {ejecutable} -m pytest"
            if tipo == "npm":
                return "npm.cmd test"
            raise ValueError("El tipo de pruebas debe ser pytest o npm.")
        raise ValueError("Operación fuera de la lista blanca.")

    @staticmethod
    def _sanear_salida(texto):
        limpio = "".join(
            caracter for caracter in (texto or "")
            if caracter in "\n\r\t" or ord(caracter) >= 32
            and not 127 <= ord(caracter) <= 159
        )
        limpio = limpio.replace("<", "&lt;").replace(">", "&gt;")
        return limpio[:10000]

    def _ejecutar_comando(self, operacion, args, comando):
        # Se propaga el código de salida de programas nativos y de cmdlets.
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            "trap { exit 1 }\n"
            f"{comando}\n"
            "if ($null -ne $LASTEXITCODE) { exit $LASTEXITCODE }\n"
        )
        codificado = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        proceso = None
        limite = 90 if operacion in _OPERACIONES_AMARILLAS else 15
        cwd = self._raiz
        if operacion == "ejecutar_tests":
            try:
                cwd = self._resolver_ruta_workspace(args.get("ruta", "."))
            except ValueError as error:
                return {"ok": False, "mensaje": str(error)}
        try:
            proceso = subprocess.Popen(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive",
                 "-EncodedCommand", codificado],
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                shell=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            stdout, stderr = proceso.communicate(timeout=limite)
            returncode = proceso.returncode
            expirado = False
        except subprocess.TimeoutExpired:
            if proceso is not None:
                try:
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", str(proceso.pid)],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        timeout=10,
                        check=False,
                        shell=False,
                    )
                    stdout, stderr = proceso.communicate(timeout=5)
                except Exception:
                    proceso.kill()
                    stdout, stderr = proceso.communicate()
            else:
                stdout, stderr = "", ""
            returncode = 124
            expirado = True
        except Exception as error:
            return {
                "ok": False,
                "mensaje": f"No pude iniciar la operación {operacion}.",
                "error": str(error),
            }

        log = (
            f"Operación: {operacion}\nCódigo de salida: {returncode}\n"
            f"STDOUT:\n{self._sanear_salida(stdout)}\n"
            f"STDERR:\n{self._sanear_salida(stderr)}"
        )
        log_confiable = f"<log_de_terminal>\n{log}\n</log_de_terminal>"
        if expirado:
            log_confiable += "\nEl tiempo límite se agotó y se terminó el árbol de procesos."

        if self._resumir_cb:
            try:
                resumen = self._resumir_cb(operacion, returncode, log_confiable)
            except Exception:
                resumen = ""
        else:
            resumen = ""
        if not resumen:
            estado = "correctamente" if returncode == 0 else "con errores"
            resumen = f"La operación {operacion} terminó {estado}."
        return {
            "ok": returncode == 0,
            "mensaje": resumen,
            "error": None if returncode == 0 else
                     f"{operacion} terminó con código {returncode}.",
            "returncode": returncode,
        }

    def ejecutar_operacion(self, operacion, args, modo):
        """Ejecuta una operación permitida para el rol de menor privilegio."""
        if not isinstance(modo, str) or modo not in _MODOS:
            return self._bloqueo("Modo de terminal no válido.")
        if not isinstance(operacion, str):
            return self._bloqueo("Operación fuera de la lista blanca.")
        if not isinstance(args, dict):
            return {"ok": False, "mensaje": "Los argumentos deben ser un objeto."}
        if self._contiene_operador(args):
            return self._bloqueo(
                "Operación bloqueada: los argumentos contienen redirecciones, "
                "tuberías o encadenamientos.")
        regla = OPERACIONES_PERMITIDAS.get(operacion)
        if regla is None:
            return self._bloqueo(
                "Operación bloqueada: no está permitida en la lista blanca.")
        if modo not in regla["modos"]:
            return self._bloqueo("Operación bloqueada para este modo.")
        if set(args) - regla["argumentos"]:
            return self._bloqueo(
                "Operación bloqueada: argumento no permitido.")
        try:
            comando = self._crear_comando(operacion, args)
        except (TypeError, ValueError) as error:
            if any(palabra in str(error).lower() for palabra in (
                    "bloquead", "lista blanca", "workspace")):
                return self._bloqueo(str(error))
            return {"ok": False, "mensaje": str(error)}

        if regla["semaforo"] == "amarillo":
            detalle = self._descripcion_operacion(operacion, args)
            pregunta = (
                f"Esta operación modificará el workspace: {detalle}. "
                "¿Autoriza que la ejecute? Responda sí o no."
            )
            pendiente = (operacion, dict(args), modo, comando)
            with self._lock:
                self._pendiente = pendiente
            pregunta = self._almacen_confirmaciones.solicitar(
                ejecutar=lambda: self._resolver_pendiente(pendiente, True),
                rechazar=lambda: self._resolver_pendiente(pendiente, False),
                al_descartar=lambda: self._descartar_pendiente(pendiente),
                pregunta=pregunta,
                origen="terminal",
                accion=operacion,
                argumentos=args,
            )
            return {
                "ok": True,
                "confirmacion_requerida": True,
                "mensaje": pregunta,
            }
        return self._ejecutar_comando(operacion, args, comando)

    @staticmethod
    def _descripcion_operacion(operacion, args):
        if operacion == "instalar_dependencia":
            return f"instalar {args.get('paquete')} con {args.get('gestor')}"
        if operacion == "crear_directorio":
            return f"crear la carpeta {args.get('ruta')}"
        if operacion == "ejecutar_tests":
            return f"ejecutar pruebas de tipo {args.get('tipo', 'pytest')}"
        return operacion

    #: Código muerto desde la fusión con `integracion-router`: la compuerta única
    #: de `handle_command` resuelve el almacén compartido para todos los orígenes,
    #: incluido `terminal`, así que nadie pregunta ya por el pendiente de la terminal.
    #: Se conservan porque `PuertoTerminal` los declara y el test de caducidad los
    #: ejerce; ETAPA 1b decidirá si salen del contrato.
    def hay_confirmacion_pendiente(self):
        return self._almacen_confirmaciones.hay_pendiente(origen="terminal")

    def procesar_confirmacion(self, respuesta):
        resultado = self._almacen_confirmaciones.resolver(
            respuesta, origen="terminal")
        if resultado is None:
            return False, ""
        return resultado.atendida, resultado.mensaje

    def _resolver_pendiente(self, pendiente, aceptar):
        with self._lock:
            if self._pendiente is not pendiente:
                return ""
            self._pendiente = None
        if not aceptar:
            return "Entendido. Cancelé la operación y no ejecuté cambios."
        operacion, args, _modo, comando = pendiente
        resultado = self._ejecutar_comando(operacion, args, comando)
        return resultado.get("mensaje", "") if isinstance(resultado, dict) else str(resultado)

    def _descartar_pendiente(self, pendiente):
        with self._lock:
            if self._pendiente is pendiente:
                self._pendiente = None

    def tool_terminal_diagnostico(self, operacion, args=None):
        """Expone únicamente consultas de diagnóstico al asistente."""
        return self.ejecutar_operacion(operacion, args or {}, "asistente")

    def tool_terminal_coder(self, operacion, args=None):
        """Expone operaciones de desarrollo con permisos de coder."""
        return self.ejecutar_operacion(operacion, args or {}, "coder")
