"""Presets de la ruta rápida del primer arranque (diseño §6).

Cada preset fija de una vez la política de las funciones de IA (conversación, órdenes,
código) y de la voz, **usando lo que la persona ya tiene en sus bibliotecas**. Un preset no
descarga ni agrega nada: si le falta una pieza (un modelo local, una voz de nube) lo dice y
no toca esa función.

  * `local`: solo modelos locales.            * `nube`: solo modelos de nube.
  * `hibrido_local`: local primero, nube de respaldo.
  * `hibrido_nube`: nube primero, local de respaldo.

Los modelos locales se reparten por rol cuando se sabe (el del catálogo declara si sirve para
conversar, entender órdenes o escribir código); si no hay uno para el rol, se usa cualquier
local. Las voces locales son las de Windows y la voz de Piper si está instalada.

Falta (a propósito): «Solo texto». Necesita un interruptor de «sin IA» y «sin voz» en el
Núcleo que todavía no existe; se anotó en el diseño.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from proveedores.llm.cadena import ordenar

from .ollama_local import ModeloCatalogo

PENSAMIENTO = "modelosPensamiento"
VOCES = "voces"
FUNCIONES_IA = (("chat", "chat", "Conversación"), ("nucleo", "nucleus", "Órdenes (núcleo)"),
                ("codigo", "coder", "Código"))


@dataclass(frozen=True)
class Preset:
    id: str
    nombre: str
    descripcion: str
    politica: str


PRESETS = (
    Preset("local", "Todo en mi equipo",
           "Solo modelos y voces de este equipo. No sale nada de su equipo.", "solo_local"),
    Preset("nube", "Todo en la nube",
           "Solo modelos y voces de sus proveedores. Lo que escribas y lo que diga D.A.R.K. se envía a ellos.",
           "solo_nube"),
    Preset("hibrido_local", "Híbrido: local primero",
           "Usa su equipo y, si falla o tarda, sus proveedores de respaldo.", "local_primero"),
    Preset("hibrido_nube", "Híbrido: nube primero",
           "Usa sus proveedores y, si fallan, su equipo de respaldo.", "nube_primero"),
)


def _rol_de(recurso: dict, catalogo: list[ModeloCatalogo]) -> str | None:
    if recurso.get("rol"):
        return str(recurso["rol"])
    etiqueta = recurso.get("etiqueta")
    return next((m.rol for m in catalogo if m.etiqueta == etiqueta), None)


def _cadena_ia(recursos: list[dict], rol: str | None, politica: str, catalogo: list[ModeloCatalogo]) -> list[dict]:
    locales = [r for r in recursos if r.get("origen") != "nube"]
    del_rol = [r for r in locales if _rol_de(r, catalogo) == rol]
    nubes = [r for r in recursos if r.get("origen") == "nube"]
    return ordenar(politica, (del_rol or locales) + nubes)


def _plan(prefs: Any, preset: Preset, catalogo: list[ModeloCatalogo]) -> dict[str, Any]:
    """Qué asignaría el preset y qué le falta. No escribe nada."""
    asignaciones: list[dict[str, Any]] = []
    faltan: list[str] = []
    avisos: list[str] = []
    pensamiento = prefs.obtener(f"bibliotecas.{PENSAMIENTO}", []) or []
    for funcion, rol, nombre in FUNCIONES_IA:
        cadena = _cadena_ia(pensamiento, rol, preset.politica, catalogo)
        if cadena:
            asignaciones.append({"destino": "pensamiento", "funcion": funcion, "nombre": nombre,
                                 "politica": preset.politica, "cadena": [r["id"] for r in cadena],
                                 "nube": any(r.get("origen") == "nube" for r in cadena)})
        else:
            lado = "de nube" if preset.politica == "solo_nube" else "local"
            faltan.append(f"{nombre}: falta un modelo {lado}.")
    voces = prefs.obtener(f"bibliotecas.{VOCES}", []) or []
    cadena_voz = ordenar(preset.politica, voces)
    if cadena_voz:
        asignaciones.append({"destino": "vozSalida", "funcion": "principal", "nombre": "Voz",
                             "politica": preset.politica, "cadena": [r["id"] for r in cadena_voz],
                             "nube": any(r.get("origen") == "nube" for r in cadena_voz)})
    else:
        lado = "de nube" if preset.politica == "solo_nube" else "local (de Windows o Piper)"
        faltan.append(f"Voz: falta una voz {lado}.")
    if preset.politica in ("local_primero", "nube_primero"):
        for a in asignaciones:
            lados = {("nube" if r.get("origen") == "nube" else "local")
                     for r in (pensamiento if a["destino"] == "pensamiento" else voces) if r["id"] in a["cadena"]}
            if len(lados) == 1:
                avisos.append(f"{a['nombre']}: solo hay un lado configurado, así que no hay respaldo.")
    return {"asignaciones": asignaciones, "faltan": faltan, "avisos": avisos}


def evaluar(prefs: Any, catalogo: list[ModeloCatalogo]) -> list[dict[str, Any]]:
    """Los presets con lo que harían ahora y lo que les falta (para pintar las tarjetas)."""
    salida = []
    for preset in PRESETS:
        plan = _plan(prefs, preset, catalogo)
        salida.append({
            "id": preset.id, "nombre": preset.nombre, "descripcion": preset.descripcion,
            "aplicable": bool(plan["asignaciones"]),
            "usaNube": any(a["nube"] for a in plan["asignaciones"]),
            "funciones": [a["nombre"] for a in plan["asignaciones"]],
            "faltan": plan["faltan"], "avisos": plan["avisos"],
        })
    return salida


class ErrorPreset(Exception):
    def __init__(self, mensaje: str) -> None:
        super().__init__(mensaje)
        self.mensaje = mensaje


def aplicar(prefs: Any, preset_id: str, catalogo: list[ModeloCatalogo], aceptado: bool, ahora: str) -> dict[str, Any]:
    """Escribe las asignaciones del preset. Devuelve el plan aplicado."""
    preset = next((p for p in PRESETS if p.id == preset_id), None)
    if preset is None:
        raise ErrorPreset("Ese preset no existe.")
    plan = _plan(prefs, preset, catalogo)
    if not plan["asignaciones"]:
        raise ErrorPreset("Este preset todavía no se puede aplicar: " + " ".join(plan["faltan"]))
    usa_nube = any(a["nube"] for a in plan["asignaciones"])
    if usa_nube and not prefs.obtener("ajustes.avisoNubeAceptado") and aceptado is not True:
        raise ErrorPreset("Falta su consentimiento: enviaré lo que usted escriba y lo que yo diga a sus "
                          "proveedores, y los usará automáticamente también como respaldo.")
    for a in plan["asignaciones"]:
        prefs.establecer_asignacion(a["destino"], a["funcion"], {"politica": a["politica"], "cadena": a["cadena"]})
    if usa_nube and not prefs.obtener("ajustes.avisoNubeAceptado"):
        prefs.establecer("ajustes.avisoNubeAceptado", ahora)
    return plan
