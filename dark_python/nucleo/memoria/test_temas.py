"""
Pruebas de memoria/temas.py (V6) — basadas en los ejemplos del documento.

Ejecutar desde dark_python/:
    python -m nucleo.memoria.test_temas
"""
import os
import tempfile

try:
    from nucleo.memoria.temas import (CAMBIO, CONTINUA, DESVIO, NUEVO, REGRESO,
                                   BRECHA_LARGA, UMBRAL_DEGRADADO, Dato,
                                   GestorContexto)
except ImportError:  # permite ejecutar el archivo como script desde dark_python/
    from nucleo.memoria.temas import (CAMBIO, CONTINUA, DESVIO, NUEVO, REGRESO,
                            BRECHA_LARGA, UMBRAL_DEGRADADO, Dato,
                            GestorContexto)


def _correr(g, frases):
    return [g.procesar(f) for f in frases]


def _con_router_y_fisica():
    g = GestorContexto()
    _correr(g, [
        "Estoy arreglando el Router de D.A.R.K.",
        "El problema parece estar en las rutas de las herramientas.",
        "Por cierto, mañana tengo un examen de física.",
    ])
    return g


# --- §1 detección de temas --------------------------------------------------
def test_mismo_tema_aunque_cambie_el_objeto_de_la_frase():
    g = GestorContexto()
    r = _correr(g, [
        "Estoy arreglando el Router de D.A.R.K.",
        "El problema parece estar en las rutas de las herramientas.",
        "El Router tiene un error. Creo que está relacionado con las "
        "herramientas que agregamos ayer.",
    ])
    assert r[0].evento == NUEVO
    assert r[1].evento == CONTINUA and r[2].evento == CONTINUA
    assert len(g.contextos()) == 1          # NO se creó otro contexto


def test_tema_nuevo_con_marcador():
    g = _con_router_y_fisica()
    assert g.resumen()["titulo"].lower().startswith("examen")
    estados = {c["titulo"]: c["estado"] for c in g.contextos()}
    assert sorted(estados.values()) == ["activo", "secundario"]


def test_recordatorio_de_tema_cambia_el_foco_y_no_contamina_con_el_anterior():
    g = GestorContexto()
    g.procesar("Por cierto, hablemos de la serie El Mentalista")

    r = g.procesar(
        "Dark, recuérdame lo que hablamos sobre el universo y su expansión"
    )

    assert r.evento in (NUEVO, REGRESO)
    assert r.cambio_activo
    assert "universo" in r.titulo.lower()
    tema_activo = next(
        linea for linea in g.bloque_prompt().splitlines()
        if "Tema activo:" in linea
    )
    assert "universo" in tema_activo.lower()
    assert "mentalista" not in tema_activo.lower()


# --- §3 y §9 secundarios y regreso -------------------------------------------
def test_regreso_explicito_recupera_estado():
    g = _con_router_y_fisica()
    r = g.procesar("Bueno, volviendo al Router...")
    assert r.evento == REGRESO and r.cambio_activo
    res = g.resumen()
    assert "router" in res["titulo"].lower()
    assert "rutas" in res["estado_actual"]           # último estado conocido
    assert "Estoy arreglando" in res["objetivo"]      # objetivo conservado
    assert "Examen" in g.bloque_prompt()              # el otro tema sigue vivo


def test_regreso_implicito_por_contenido():
    g = _con_router_y_fisica()
    r = g.procesar("El router sigue fallando con las herramientas nuevas")
    assert r.evento == REGRESO and "router" in r.titulo.lower()


def test_volvamos_a_secas_va_al_anterior():
    g = _con_router_y_fisica()
    r = g.procesar("volvamos a lo de antes")
    assert r.evento == REGRESO and "router" in r.titulo.lower()


# --- §6 desvíos cortos --------------------------------------------------------
def test_desvio_corto_no_crea_ni_mueve_nada():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    n = len(g.contextos())
    r = g.procesar("Espera, ¿qué hora es?")
    assert r.evento == DESVIO and not r.cambio_activo
    r2 = g.procesar("Bueno, sigamos con el Router")
    assert r2.evento == CONTINUA and not r2.cambio_activo
    assert len(g.contextos()) == n


def test_acuses_no_cambian_nada():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    for f in ["ok", "gracias", "vale"]:
        assert g.procesar(f).evento == CONTINUA
    assert len(g.contextos()) == 1


# --- §7 y §8 cambio prolongado, maduración gradual -----------------------------
def test_cambio_prolongado_sin_marcador():
    """V2.1: anunciar una intención en OTRO campo ("necesito estudiar física")
    crea el tema de inmediato: es evidencia doble (intención + campo distinto)."""
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Las rutas de las herramientas fallan",
                "Creo que es un error de import"])
    r1 = g.procesar("Necesito estudiar física para el examen")
    assert r1.evento == NUEVO and r1.cambio_activo
    assert g.procesar("Revisa los imports del router").evento == REGRESO
    assert len(g.contextos()) == 2


def test_un_desvio_aislado_no_se_convierte_en_tema():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Las rutas de las herramientas fallan"])
    g.procesar("Hoy fui al colegio")                          # candidato, sin intención
    for f in ["Revisa los imports del router",
              "El error sale en el archivo de herramientas",
              "Prueba con otra ruta"]:
        g.procesar(f)
    assert len(g.contextos()) == 1                            # el candidato murió


# --- frases reales de voz: sin puntuación, sin tildes, corto -------------------
def test_voz_realista_tema_corto_de_otro_campo():
    g = GestorContexto()
    _correr(g, ["estoy arreglando el router de dark",
                "el problema esta en las rutas de las herramientas"])
    r1 = g.procesar("mañana tengo examen de fisica")           # 2 palabras + intención
    assert r1.evento == NUEVO and "examen" in r1.titulo.lower()
    g.procesar("tengo que estudiar cinematica")
    id_router = next(c["id"] for c in g.contextos() if c["estado"] == "secundario")
    assert not any("cinem" in p for p in g.resumen(id_router)["pendientes"])


def test_el_nombre_del_asistente_no_es_un_tema():
    g = GestorContexto()
    g.procesar("estoy arreglando el router de dark")
    g.procesar("dark cuentame un chiste de gatos")     # 'dark' no ancla al Router
    assert all("dark" not in c["titulo"].lower() for c in g.contextos())


# --- §4 y F información central vs pasajera -------------------------------------
def test_lo_pasajero_no_se_guarda_y_lo_central_si():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    g.procesar("Creo que voy a tomar agua")
    g.procesar("Falta arreglar las rutas de las herramientas")
    g.procesar("Decidimos usar rutas absolutas en el router")
    res = g.resumen()
    todo = " ".join(res["pendientes"] + res["decisiones"] + [res["objetivo"]])
    assert "agua" not in todo
    assert any("rutas" in p for p in res["pendientes"])
    assert any("absolutas" in d for d in res["decisiones"])


def test_pendiente_se_cierra_cuando_se_resuelve():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    g.procesar("Falta arreglar las rutas de las herramientas")
    assert g.resumen()["pendientes"]
    g.procesar("Ya arreglé las rutas de las herramientas")
    assert not g.resumen()["pendientes"]


# --- acciones (comandos/menús) ----------------------------------------------------
def test_los_comandos_no_crean_temas():
    g = GestorContexto()
    r = g.procesar("abre spotify", tipo="comando")
    assert r.evento == DESVIO and g.contextos() == []
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    g.procesar("abre el archivo del router", tipo="comando")
    assert len(g.contextos()) == 1


# --- §10, §15, §18 paralelos, límite, no borrar ---------------------------------
def test_limite_archiva_no_borra():
    g = GestorContexto()
    temas = ["examen de física", "el robot con servos", "la canción de Spotify",
             "el viaje familiar", "la película de anime", "el router de dark",
             "la impresora y la placa", "el almuerzo con mamá"]
    for t in temas:
        g.procesar(f"Por cierto, hablemos de {t}")
    estados = [c["estado"] for c in g.contextos()]
    assert estados.count("activo") == 1
    assert estados.count("archivado") >= 1                # se archivó, no se borró
    assert len(g.contextos()) == len(temas)
    # y un tema archivado sigue siendo recuperable por nombre
    r = g.procesar("volvamos a la impresora")
    assert r.evento in (REGRESO, CONTINUA)


def test_bloque_prompt_es_corto_y_vacio_sin_tema():
    g = GestorContexto()
    assert g.bloque_prompt() == ""
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Falta arreglar las rutas de las herramientas",
                "Decidimos usar rutas absolutas en el router",
                "Por cierto, mañana tengo un examen de física",
                "Por cierto, quiero armar un robot con servos"])
    assert 0 < len(g.bloque_prompt()) <= 650


# --- serialización (preparación V2+) ---------------------------------------------
def test_roundtrip():
    g = _con_router_y_fisica()
    g.procesar("Falta arreglar las rutas de las herramientas")
    g2 = GestorContexto()
    g2.from_dict(g.to_dict())
    assert g2.resumen() == g.resumen()
    assert g2.contextos() == g.contextos()
    assert g2.procesar("Por cierto, hablemos de música").evento == NUEVO


# --- pregunta genérica no contamina ningún tema -------------------------------
def test_pregunta_generica_no_se_guarda():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    n_perfil_antes = len(g._ctxs[1].perfil)
    r = g.procesar("¿Qué es un mutex?")
    assert r.evento == DESVIO and not r.cambio_activo
    assert len(g._ctxs[1].perfil) == n_perfil_antes    # nada nuevo se guardó
    assert len(g.contextos()) == 1                     # y no creó un tema aparte


# --- cierre explícito de tema --------------------------------------------------
def test_cierre_explicito_baja_prioridad_sin_borrar():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    r = g.procesar("Bueno, ya terminamos con esto por hoy")
    assert r.evento == DESVIO and r.contexto_id == 1
    assert g.resumen() is None                     # ya no hay tema activo
    estados = {c["id"]: c["estado"] for c in g.contextos()}
    assert estados[1] == "secundario"               # se conserva, no se borra
    # y sigue siendo recuperable
    r2 = g.procesar("El router sigue con problemas de rutas")
    assert r2.evento == REGRESO and r2.contexto_id == 1


def test_despues_de_cerrar_un_tema_nuevo_no_choca():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    g.procesar("ya terminamos con esto por ahora")
    r = g.procesar("Quiero armar un robot con servos y arduino")
    assert r.evento == NUEVO


# --- vocabulario nuevo sin campo conocido ---------------------------------------
def test_tema_sin_campo_conocido_tambien_madura():
    """Intención sobre un asunto fuera de todo campo: candidato que exige más
    certeza; ya NO se crea por mero vocabulario nuevo (eso fabricaba temas)."""
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    r1 = g.procesar("quiero montar mi iguana en la bicicleta")
    assert r1.evento == DESVIO and "sin campo" in r1.motivo
    r2 = g.procesar("hay que llevar la bicicleta de la iguana al taller")
    assert r2.evento == CAMBIO and "iguana" in r2.titulo.lower()
    # y vocabulario nuevo SIN intención no fabrica nada
    g2 = GestorContexto()
    _correr(g2, ["Estoy arreglando el Router de D.A.R.K.",
                 "mi iguana bicicleta necesita una revision urgente"])
    assert len(g2.contextos()) == 1


# --- origen queda en el resultado, sin separar contextos ------------------------
def test_origen_no_separa_contextos():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.", origen="voz")
    r = g.procesar("las rutas siguen fallando", origen="modulo")
    assert r.origen == "modulo"
    assert len(g.contextos()) == 1


# --- persistencia entre "ejecuciones" -------------------------------------------
def test_persistencia_entre_ejecuciones():
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "temas.json")
        g1 = GestorContexto(ruta_persistencia=ruta)
        g1.procesar("Estoy arreglando el Router de D.A.R.K.")
        g1.procesar("Falta arreglar las rutas de las herramientas")
        assert os.path.exists(ruta)

        g2 = GestorContexto(ruta_persistencia=ruta)   # "reinicio" del proceso
        assert "router" in g2.resumen()["titulo"].lower()
        assert g2.resumen()["pendientes"]


def test_sin_ruta_no_toca_disco():
    g = GestorContexto()          # sin ruta_persistencia ni ruta_log
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    assert g._ruta_persistencia is None and g._ruta_log is None


def test_log_registra_cada_turno():
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "log.jsonl")
        g = GestorContexto(ruta_log=ruta)
        g.procesar("Estoy arreglando el Router de D.A.R.K.")
        g.procesar("Por cierto, mañana tengo un examen de física.")
        with open(ruta, encoding="utf-8") as f:
            lineas = f.readlines()
        assert len(lineas) == 2
        import json as _json
        assert _json.loads(lineas[-1])["evento"] == NUEVO


# =====================================================================
#  V2 — MADURACIÓN
# =====================================================================
def _id_por_titulo(g, fragmento):
    return next(c["id"] for c in g.contextos()
                if fragmento in c["titulo"].lower())


def test_v2_cada_tipo_decae_a_su_ritmo():
    dec = Dato("decision", "x", [], 1.0, 0)
    det = Dato("detalle", "x", [], 1.0, 0)
    assert dec.relevancia(0) == det.relevancia(0) == 1.0
    assert dec.relevancia(20) > 0.9            # una decisión casi no se mueve
    assert det.relevancia(20) < 0.3            # un detalle ya casi murió
    assert det.relevancia(20) < dec.relevancia(20)


def test_v2_tema_viejo_con_muchas_decisiones_pierde_frente_a_uno_reciente():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Decidimos usar rutas absolutas en el router",
                "Falta arreglar las rutas de las herramientas del router",
                "El problema es el import circular en el router"])
    g._turno += 300                                        # mucho tiempo después
    g.procesar("Por cierto, quiero armar un robot con servos")
    g.procesar("Decidimos usar servos pequeños en el robot")
    viejo = _id_por_titulo(g, "router")
    nuevo = next(c["id"] for c in g.contextos() if c["id"] != viejo)
    assert g._prioridad(g._ctxs[nuevo]) > g._prioridad(g._ctxs[viejo])
    # y el viejo, por muchas decisiones que tenga, sigue existiendo
    assert g._ctxs[viejo].datos


def test_v2_recurrencia_cuenta_regresos_y_no_nuevos():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    assert g._ctxs[1].veces_retomado == 0                  # NUEVO no cuenta
    for _ in range(3):
        g.procesar("Por cierto, mañana tengo un examen de física")
        g.procesar("Bueno, volviendo al Router...")
    assert g._ctxs[1].veces_retomado == 3


def test_v2_mas_retomado_gana_a_igualdad_de_todo_lo_demas():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Por cierto, quiero armar un robot con servos"])
    a, b = g._ctxs[1], g._ctxs[2]
    for c in (a, b):                       # igualo todo salvo la recurrencia
        c.ultimo_turno, c.turnos, c.datos = g._turno, 5, []
    a.veces_retomado, b.veces_retomado = 4, 0
    assert g._prioridad(a) > g._prioridad(b)


def test_v2_muerte_suave_oculta_pero_no_borra():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "El problema es el import circular en el router"])
    assert g.resumen()["hallazgos"]
    n = len(g._ctxs[1].datos)
    g._turno += 400                        # el hallazgo cae bajo el umbral
    assert not g.resumen()["hallazgos"]                    # ya no se muestra
    assert len(g._ctxs[1].datos) == n                      # pero sigue guardado
    assert all(d.relevancia(g._turno) < UMBRAL_DEGRADADO
               for d in g._ctxs[1].datos if d.tipo == "hallazgo")


def test_v2_el_mas_relevante_gana_al_de_mayor_peso_crudo():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    for _ in range(3):                     # refuerzo: peso crudo alto (4.0)
        g.procesar("El problema es el import circular en herramientas del router")
    g._turno += 40                         # ...pero pasa el tiempo
    g.procesar("El error viene del archivo de rutas del router")   # peso 3.0
    assert "rutas" in g.resumen()["hallazgos"][0]          # el vigente va primero


def test_v2_regreso_tras_brecha_larga_lo_dice_el_prompt():
    g = _con_router_y_fisica()
    g._turno += BRECHA_LARGA + 5
    r = g.procesar("Bueno, volviendo al Router...")
    assert r.evento == REGRESO and r.brecha >= BRECHA_LARGA
    assert "Hacía un rato" in g.bloque_prompt()


def test_v2_regreso_corto_no_agrega_aviso():
    g = _con_router_y_fisica()
    r = g.procesar("Bueno, volviendo al Router...")
    assert r.evento == REGRESO and r.brecha < BRECHA_LARGA
    assert "Hacía un rato" not in g.bloque_prompt()


def test_v2_perfil_decaido_ya_no_roba_activaciones():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "El problema parece estar en las rutas de las herramientas",
                "Las herramientas fallan en las rutas",
                "Por cierto, mañana tengo un examen de física"])
    g2 = GestorContexto()
    g2.from_dict(g.to_dict())              # misma conversación, dos futuros
    g2._turno += 600
    frase = "revisa las herramientas y las rutas"
    assert g.procesar(frase).evento == REGRESO             # reciente: retoma
    assert g2.procesar(frase).evento != REGRESO            # viejo: ya no atrae


def test_v2_el_objetivo_conserva_identidad_pese_al_decaimiento():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Las herramientas fallan en las rutas",
                "Por cierto, mañana tengo un examen de física"])
    g._turno += 600
    r = g.procesar("volvamos al router")                   # nombra el objetivo
    assert r.evento == REGRESO and "router" in r.titulo.lower()


def test_v2_titulo_se_recalcula_una_sola_vez():
    g = GestorContexto()
    frases = ["Estoy arreglando el Router de D.A.R.K.",
              "Las rutas de las herramientas fallan",
              "El router no encuentra las herramientas",
              "Creo que es un error de import en el router",
              "Las rutas del router siguen fallando"]
    _correr(g, frases)
    assert g._ctxs[1].titulo_fijado
    titulo = g._ctxs[1].titulo
    _correr(g, ["El router falla con las rutas otra vez",
                "Revisa los imports del router"])
    assert g._ctxs[1].titulo == titulo                     # no vuelve a cambiar


def test_v2_estado_v1_guardado_sigue_cargando():
    """Un JSON escrito por V1 (sin los campos nuevos) debe cargar sin migrar."""
    g = _con_router_y_fisica()
    d = g.to_dict()
    for c in d["contextos"]:
        c.pop("veces_retomado", None)
        c.pop("titulo_fijado", None)
    g2 = GestorContexto()
    g2.from_dict(d)
    assert g2._ctxs[1].veces_retomado == 0
    assert g2.procesar("Bueno, volviendo al Router").evento == REGRESO


# =====================================================================
#  V2.1 — ACTOS DE HABLA, EVIDENCIA PARA CREAR TEMAS, SEPARACIÓN FINA
# =====================================================================
ACCIONES_T = ["Sube el volumen del TV", "Abre Netflix", "Pon música", "Apaga la luz",
              "Cambia de canal", "Baja el volumen", "Silencia la tele",
              "¿Puedes subir el volumen?", "Me puedes poner música",
              "Quiero ver una película", "Llama a mi hermano"]
PUNTUALES_T = ["¿Qué es un mutex?", "¿Quién fue Newton?", "¿Cuál es la capital de Australia?",
               "Cuéntame un chiste", "¿Por qué el cielo es azul?", "¿Cómo se dice perro en inglés?"]
PASAJEROS_T = ["Voy a tomar agua", "Tengo sueño", "Ya vengo", "Me duele un poco la cabeza",
               "Se me cayó el lápiz", "Qué calor hace"]
META_T = ["Hola Dark", "¿Me escuchas?", "Buenas noches", "Gracias Dark", "Ajá", "Jaja",
          "¿Quién eres?", "Hasta luego"]


def _no_toca_nada(g, frase, tipo="charla"):
    n = len(g.contextos()); act = g._activo_id
    turnos = sum(c.turnos for c in g._ctxs.values())
    g.procesar(frase, tipo=tipo)
    assert len(g.contextos()) == n, frase
    assert g._activo_id == act, frase
    assert sum(c.turnos for c in g._ctxs.values()) == turnos, frase


def test_v21_acciones_no_crean_ni_contaminan_en_frio_ni_con_tema():
    for f in ACCIONES_T:
        _no_toca_nada(GestorContexto(), f)                      # en frío
        g = _con_router_y_fisica()
        g.procesar("Bueno, volviendo al Router")
        _no_toca_nada(g, f)                                     # durante un tema


def test_v21_preguntas_puntuales_transitorios_y_meta_no_tocan_el_tema():
    for f in PUNTUALES_T + PASAJEROS_T + META_T:
        _no_toca_nada(GestorContexto(), f)
        g = _con_router_y_fisica()
        g.procesar("Bueno, volviendo al Router")
        _no_toca_nada(g, f)


def test_v21_marcador_mas_pregunta_puntual_es_desvio_no_tema():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    r = g.procesar("Por cierto, ¿qué es un mutex?")
    assert r.evento == DESVIO and len(g.contextos()) == 1
    r = g.procesar("Oye, ¿qué hora es?")
    assert r.evento == DESVIO


def test_v21_pregunta_sobre_el_propio_tema_si_continua():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Creo que es un error de import en el router"])
    for f in ["¿Por qué falla el router?", "¿Qué es el import circular del router?"]:
        r = g.procesar(f)
        assert r.evento == CONTINUA and "acto" not in r.motivo, f


def test_v21_trabajo_real_con_verbos_de_control_no_se_traga():
    g = GestorContexto()
    _correr(g, ["Quiero desarrollar el módulo TV", "El módulo TV controla el volumen"])
    for f in ["Cambia el canal por defecto en la configuración del módulo TV",
              "Abre el archivo de configuración del módulo TV",
              "Pon el volumen inicial del módulo TV en treinta"]:
        assert not g.procesar(f).motivo.startswith("acto:"), f
    g = GestorContexto()
    _correr(g, ["Quiero armar una playlist para la fiesta", "Hay que meter canciones de salsa"])
    assert not g.procesar("Pon primero las canciones más bailables de la playlist"
                          ).motivo.startswith("acto:")
    # pero la orden pura sobre el dispositivo sigue siendo orden aunque el tema sea TV
    g = GestorContexto()
    _correr(g, ["Quiero desarrollar el módulo TV", "El módulo TV controla el volumen"])
    assert g.procesar("Sube el volumen del TV").motivo == "acto:accion"


def test_v21_mensaje_aislado_no_crea_tema_pero_la_intencion_si():
    g = GestorContexto()
    r = g.procesar("Hoy fui al colegio")
    assert r.evento == DESVIO and g.contextos() == []           # solo candidato
    g = GestorContexto()
    assert g.procesar("Estoy trabajando en el módulo TV").evento == NUEVO
    g = GestorContexto()
    assert g.procesar("Quiero desarrollar el módulo TV").evento == NUEVO


def test_v21_continuidad_convierte_un_candidato_en_tema():
    g = GestorContexto()
    g.procesar("Hoy fui al colegio")
    r = g.procesar("En el colegio estudiamos matemáticas")
    assert r.evento == CAMBIO and len(g.contextos()) == 1


def test_v21_subproyectos_del_mismo_dominio_no_se_funden():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Las rutas de las herramientas fallan",
                "Por cierto, quiero desarrollar el módulo de teléfono",
                "El módulo de teléfono debe recibir llamadas",
                "Por cierto, estoy trabajando en el módulo TV",
                "El módulo TV debe controlar el volumen"])
    titulos = sorted(c["titulo"].lower() for c in g.contextos())
    assert len(titulos) == 3
    assert g.procesar("Volvamos al router, sigue el error de rutas").evento == REGRESO
    assert "router" in g.resumen()["titulo"].lower()
    assert g.procesar("Volvamos al módulo de teléfono").evento == REGRESO
    assert "tel" in g.resumen()["titulo"].lower()


def test_v21_titulos_sin_verbos_de_trabajo():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    assert g.resumen()["titulo"].lower() == "router"


def test_v21_siglas_y_sinonimos():
    g = GestorContexto()
    _correr(g, ["Estoy trabajando en el módulo TV", "El módulo TV controla el volumen"])
    assert g.procesar("El televisor se desconecta a veces").evento == CONTINUA
    assert g.procesar("La tele no responde al módulo").evento == CONTINUA
    assert len(g.contextos()) == 1


def test_v21_alias_de_voz_y_cortesia():
    for f in ["hey dark sube el volumen", "dark pon musica por favor", "ey dark cambia de canal"]:
        _no_toca_nada(GestorContexto(), f)


def test_v21_tarea_larga_se_trata_como_accion():
    g = GestorContexto()
    assert g.procesar("Escríbeme un resumen de la revolución francesa",
                      tipo="tarea_larga").evento == DESVIO
    assert g.contextos() == []


def test_v21_cierre_nombrado_y_correccion():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el Router de D.A.R.K.",
                "Las rutas de las herramientas fallan",
                "Por cierto, estoy trabajando en el módulo TV",
                "El módulo TV controla el volumen"])
    r = g.procesar("No, perdón, me refería al router")          # corrección
    assert r.evento == REGRESO and "router" in r.titulo.lower()
    r = g.procesar("ya no quiero seguir con el módulo TV")      # cierre por nombre
    assert "tema cerrado" in r.motivo
    estados = {c["titulo"].lower(): c["estado"] for c in g.contextos()}
    assert any("tv" in t and e == "secundario" for t, e in estados.items())
    assert g.resumen()["titulo"].lower() == "router"            # el activo no cambió


def test_v21_sin_evidencia_no_se_absorbe_pero_el_hilo_sigue():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    n = len(g._ctxs[1].perfil)
    r = g.procesar("Se me cayó el lápiz")
    assert r.evento != NUEVO and len(g._ctxs[1].perfil) == n
    # pero un pendiente/decisión sin palabra en común SÍ se guarda (contenido de trabajo)
    g.procesar("Falta hacer pruebas con los datos viejos")
    assert any("pruebas" in p for p in g.resumen()["pendientes"])


def test_v21_cadena_de_marcadores_no_filtra_palabras_al_perfil():
    g = GestorContexto()
    for t in ["examen de física", "el robot con servos", "la película de anime"]:
        g.procesar(f"Por cierto, hablemos de {t}")
    assert len(g.contextos()) == 3
    assert all("hablemos" not in c["titulo"].lower() for c in g.contextos())


def test_v21_candidato_visible_en_el_prompt_si_hay_intencion():
    g = GestorContexto()
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    for _ in range(3):
        g.procesar("Las rutas de las herramientas fallan en el router")
    g.procesar("Quiero desarrollar el módulo TV")               # mismo campo: candidato
    assert "Posible cambio de tema" in g.bloque_prompt()


# =====================================================================
#  HALLAZGOS DEL LOG REAL (sesión con voz, Whisper y clasificador reales)
# =====================================================================
def test_log_eco_del_prompt_de_whisper_es_ruido():
    g = _con_router_y_fisica()
    g.procesar("Bueno, volviendo al Router")
    _no_toca_nada(g, "el usuario dicta frases cortas en español")
    _no_toca_nada(GestorContexto(), "el usuario dicta frases cortas en español")


def test_log_quejas_al_asistente_no_se_pegan_a_ningun_tema():
    for f in ["Esto está muy mal", "No tiene sentido", "Ok, te me calmas. tranquilo",
              "¡ugh", "No me entiendes"]:
        _no_toca_nada(GestorContexto(), f)
        g = _con_router_y_fisica()
        g.procesar("Bueno, volviendo al Router")
        _no_toca_nada(g, f)


def test_log_orden_con_pronombre_pegado_no_es_tema():
    """'apágame el televisor porfa' llegó como charla y terminó como tema activo."""
    for f in ["Oye, apagame el televisor porfa", "Ponme música", "Súbeme el volumen"]:
        _no_toca_nada(GestorContexto(), f)
        g = _con_router_y_fisica()
        g.procesar("Bueno, volviendo al Router")
        _no_toca_nada(g, f)


def test_log_muletillas_no_entran_al_titulo():
    g = GestorContexto()
    g.procesar("Nada, solamente estoy arreglando algunos problemas de la aplicación")
    titulo = g.resumen()["titulo"].lower()
    assert "nada" not in titulo and "algunos" not in titulo and "solamente" not in titulo


def test_log_el_tema_real_se_reconoce_entre_basura_de_voz():
    g = GestorContexto()
    for f in ["Esto está muy mal", "una cosa esta canción es buena", "¡ugh",
              "nada, solamente estoy teniendo unos problemitas", "con una aplicación"]:
        assert g.procesar(f).evento != NUEVO, f
    r = g.procesar("hay algunos problemas con una aplicación que estoy desarrollando")
    assert r.evento == NUEVO and "aplicaci" in r.titulo.lower()
    assert g.procesar("oye, apagame el televisor porfa").motivo == "acto:accion"
    assert len(g.contextos()) == 1


def test_log_estado_viejo_arranca_sin_tema_activo_pero_recuperable():
    import json as _json
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "temas.json")
        g = _con_router_y_fisica()
        g.procesar("Bueno, volviendo al Router")
        viejo = g.to_dict()
        viejo.pop("ts", None)                         # JSON escrito por una versión sin reloj
        for c in viejo["contextos"]:
            c.pop("ultimo_ts", None)
        _json.dump(viejo, open(ruta, "w"))
        g2 = GestorContexto(ruta_persistencia=ruta)
        assert g2.resumen() is None and len(g2.contextos()) == 2   # nada activo, nada perdido
        assert g2.procesar("Bueno, volviendo al Router").evento == REGRESO


def test_log_estado_reciente_conserva_el_tema_activo():
    import json as _json, time as _time
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "temas.json")
        g = GestorContexto(ruta_persistencia=ruta)
        g.procesar("Estoy arreglando el Router de D.A.R.K.")
        g2 = GestorContexto(ruta_persistencia=ruta)                # reinicio inmediato
        assert g2.resumen() is not None
        datos = _json.load(open(ruta)); datos["ts"] = _time.time() - 7200   # hace 2 horas
        _json.dump(datos, open(ruta, "w"))
        assert GestorContexto(ruta_persistencia=ruta).resumen() is None


def test_log_inactividad_larga_enfria_el_tema_activo():
    reloj = [1000.0]
    g = GestorContexto(reloj=lambda: reloj[0])
    g.procesar("Estoy arreglando el Router de D.A.R.K.")
    reloj[0] += 600                                    # 10 min: sigue activo
    assert g.procesar("Las rutas de las herramientas fallan").evento == CONTINUA
    reloj[0] += 3600                                   # 1 hora de silencio
    r = g.procesar("Las rutas del router siguen fallando")
    assert r.evento == REGRESO and r.cambio_activo     # se retoma, no se asume vigente


def test_log_poda_de_temas_flojos_y_olvidados():
    reloj = [1000.0]
    g = GestorContexto(reloj=lambda: reloj[0])
    g.procesar("Quiero armar un robot con servos")     # una sola frase, sin decisiones
    g.procesar("Por cierto, estoy trabajando en el módulo TV")
    assert len(g.contextos()) == 2
    reloj[0] += 13 * 3600
    g.procesar("El módulo TV controla el volumen")
    assert [c["titulo"].lower() for c in g.contextos()] == ["módulo tv"] or \
           all("robot" not in c["titulo"].lower() for c in g.contextos())


def test_log_un_tema_con_decisiones_nunca_se_poda():
    reloj = [1000.0]
    g = GestorContexto(reloj=lambda: reloj[0])
    g.procesar("Quiero armar un robot con servos")
    g.procesar("Decidimos usar baterías de litio en el robot")
    g.procesar("Por cierto, estoy trabajando en el módulo TV")
    reloj[0] += 30 * 3600
    g.procesar("El módulo TV controla el volumen")
    assert any("robot" in c["titulo"].lower() for c in g.contextos())


def test_log_tema_viejo_y_flojo_no_sale_en_el_prompt_al_llm():
    reloj = [1000.0]
    g = GestorContexto(reloj=lambda: reloj[0])
    g.procesar("Quiero armar un robot con servos")                 # flojo
    g.procesar("Por cierto, estoy trabajando en el módulo TV")
    reloj[0] += 3 * 3600                                           # fuera de RECIENTE
    g.procesar("El módulo TV controla el volumen")
    bloque = g.bloque_prompt()
    assert "módulo tv" in bloque.lower() and "robot" not in bloque.lower()


def test_log_secundario_reciente_si_se_menciona():
    g = _con_router_y_fisica()                                     # reloj real: todo reciente
    g.procesar("Bueno, volviendo al Router")
    assert "xamen" in g.bloque_prompt()


# --- V3 · paralelismo ---------------------------------------------------------
def _dos_lineas():
    g = GestorContexto()
    _correr(g, [
        "Estoy arreglando el router de Dark",
        "El router no encuentra la herramienta de volumen",
        "Mañana tengo un examen de física",
        "Tengo que repasar cinemática y velocidad",
    ])
    return g


def test_v3_alternar_entre_lineas_sin_marcador_las_separa():
    g = _dos_lineas()
    r = g.procesar("El problema del router es el import del clasificador")
    assert r.evento == REGRESO and "outer" in r.titulo.lower()
    r = g.procesar("La fórmula de velocidad media me confunde")
    assert r.evento == REGRESO and "outer" not in r.titulo.lower()


def test_v3_linea_reciente_es_paralela_y_dormida_no():
    g = _dos_lineas()
    roles = [l["rol"] for l in g.lineas()]
    assert "paralela" in roles and "activa" in roles
    g._turno += 100
    assert all(l["rol"] != "paralela" for l in g.lineas())


def test_v3_alternancia_no_infla_la_recurrencia():
    g = _dos_lineas()
    for _ in range(3):
        g.procesar("El router tiene un problema con el import del clasificador")
        r = g.procesar("Me falta practicar velocidad y cinemática")
    assert r.alternancia
    assert all(c.veces_retomado == 0 for c in g._ctxs.values())
    assert any(c.alternancias >= 2 for c in g._ctxs.values())


def test_v3_mensaje_que_toca_dos_lineas_por_igual_no_se_absorbe():
    g = _dos_lineas()
    antes = {c.id: (c.turnos, len(c.datos)) for c in g._ctxs.values()}
    r = g.procesar("La herramienta y la cinemática se mezclan")
    despues = {c.id: (c.turnos, len(c.datos)) for c in g._ctxs.values()}
    assert r.ambiguo and antes == despues
    assert "pudo ser" in g.bloque_prompt()


def test_v3_mientras_tanto_declara_linea_paralela_y_la_protege():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el router de Dark",
                "El router no encuentra la herramienta de volumen"])
    r = g.procesar("Mientras tanto estoy armando un robot con servos")
    assert r.evento == NUEVO and "paralela" in r.motivo
    assert all(c.paralelo for c in g._ctxs.values())
    assert "Líneas en paralelo" in g.bloque_prompt()


def test_v3_linea_paralela_se_archiva_despues_que_una_dormida():
    g = _dos_lineas()
    par = [c for c in g._ctxs.values() if g._es_paralelo(c)][0]
    d = g._nuevo_ctx("Playlist musica canciones"); d.id = 99; d.turnos = 3
    d.estado = "secundario"; d.ultimo_turno = -50 + g._turno; g._ctxs[99] = d
    g._turno += 40                       # la dormida deja de ser reciente
    par.paralelo, par.ultimo_turno = True, g._turno - 3
    assert g._es_paralelo(par) and not g._es_paralelo(d)
    import nucleo.memoria.temas as m
    viejo = m.MAX_CONTEXTOS_VIVOS
    m.MAX_CONTEXTOS_VIVOS = 2
    try:
        g._aplicar_limite()
    finally:
        m.MAX_CONTEXTOS_VIVOS = viejo
    assert g._ctxs[99].estado == "archivado" and par.estado != "archivado"


def test_v3_mismo_campo_no_funde_proyectos_paralelos():
    g = GestorContexto()
    _correr(g, ["Estoy arreglando el router de Dark",
                "El router devuelve la ruta equivocada para el clasificador",
                "Hay que revisar los logs del router",
                "Quiero desarrollar el módulo de la TV",
                "El módulo de la tele necesita el puerto del televisor"])
    titulos = [c["titulo"].lower() for c in g.contextos()]
    assert len(titulos) == 2 and any("tv" in t or "tele" in t for t in titulos)


def test_v3_estado_v2_guardado_sigue_cargando():
    g = _dos_lineas()
    d = g.to_dict()
    for c in d["contextos"]:
        c.pop("paralelo", None); c.pop("alternancias", None)
    g2 = GestorContexto(); g2.from_dict(d)
    assert g2.resumen() is not None and g2._ctxs[1].paralelo is False


def test_v3_log_pedido_de_musica_con_gusto_no_se_pega_a_otro_tema():
    g = GestorContexto()
    _correr(g, ["te pareceria algo malo si hago que tus servicios se hagan publicos para el mundo",
                "no te gustaria que yo le muestre el sistema que he creado a otras personas"])
    r = g.procesar("oye, me gustaria escuchar musica tranquila mientras trabajo")
    assert r.motivo == "acto:accion"
    assert "music" not in g._activo().perfil if g._activo() else True


def test_v3_log_ordenes_largas_y_peticiones_de_estilo_no_son_tema():
    g = GestorContexto()
    for f in ["quiero que me configures un fondo de pantalla en mi computador estilo agujero negro",
              "cambiala por algo mas instrumental, como can you hear the music",
              "puedes hablar un poco menos profesional"]:
        r = g.procesar(f)
        assert r.motivo.startswith("acto:") or r.motivo == "acción", (f, r)
    assert g.contextos() == []


def test_v3_log_especificamente_no_es_el_campo_codigo():
    g = GestorContexto()
    assert "codigo" not in g._campos_de(__import__('nucleo.memoria.temas', fromlist=['x'])._stems('mas especificamente violin'))


def test_v3_log_gusto_musical_nuevo_se_vuelve_su_propio_tema():
    g = GestorContexto()
    _correr(g, ["no te gustaria que yo le muestre el sistema que he creado al mundo",
                "el mundo deberia conocer el sistema y a las personas que lo usan"])
    _correr(g, ["me gusta la musica instrumental, mas especificamente violin y piano",
                "quiero escuchar it's raining somewhere else de undertale",
                "esa cancion de undertale es de piano y violin"])
    assert any("music" in c["titulo"].lower() or "piano" in c["titulo"].lower()
               or "violin" in c["titulo"].lower() or "undertale" in c["titulo"].lower()
               for c in g.contextos())


# --- V4 · intersecciones ------------------------------------------------------
def _router_y_tv():
    g = GestorContexto()
    _correr(g, [
        "Estoy arreglando el router de Dark",
        "El router devuelve la ruta equivocada para el clasificador",
        "Quiero desarrollar el módulo de la TV",
        "El módulo de la tele necesita el puerto del televisor",
        "Vamos a definir los canales favoritos de la tele",
    ])
    assert len(g.contextos()) == 2
    return g


def test_v4_mensaje_con_verbo_de_relacion_y_vocabulario_de_ambos_registra():
    g = _router_y_tv()
    antes = g.resumen()["titulo"]
    r = g.procesar("El router afecta al puerto del televisor")
    rels = g.relaciones()
    assert len(rels) == 1 and "afecta" in rels[0]["categorias"]
    assert r.interseccion and "acaba de relacionar" in g.bloque_prompt()
    assert r.titulo and antes   # la asignación del mensaje sigue su curso normal


def test_v4_co_mencion_sin_verbo_no_basta_ni_repetida():
    g = _router_y_tv()
    g.procesar("El router y el puerto del televisor")
    assert g.relaciones() == []                      # un indicio no es relación
    for _ in range(3):                               # repetir la frase no es evidencia nueva
        g.procesar("El router y el puerto del televisor")
    assert g.relaciones() == []


def test_v4_palabra_compartida_o_un_solo_tema_no_relaciona():
    g = _router_y_tv()
    for f in ["El error está en el archivo", "Hay un problema con el puerto",
              "Falta probar el router con comandos largos",
              "Los canales favoritos de la tele"]:
        g.procesar(f)
    assert g.relaciones() == []


def test_v4_la_relacion_queda_en_ambos_temas_y_sobrevive_al_guardado():
    g = _router_y_tv()
    g.procesar("Vamos a usar el router para el módulo de la TV")
    assert all(len(c.relaciones) == 1 for c in g._ctxs.values())
    g2 = GestorContexto(); g2.from_dict(g.to_dict())
    assert g2.relaciones() == g.relaciones()


def test_v4_prompt_menciona_la_relacion_cuando_el_tema_vuelve():
    g = _router_y_tv()
    g.procesar("Vamos a usar el router para el módulo de la TV")
    g.procesar("Bueno, volviendo al router...")
    g.procesar("Falta revisar la ruta del clasificador")
    p = g.bloque_prompt()
    assert "Relacionado con" in p and "uso" in p


def test_v4_tema_borrado_no_deja_relaciones_colgando():
    g = _router_y_tv()
    g.procesar("Vamos a usar el router para el módulo de la TV")
    ids = [c.id for c in g._ctxs.values()]
    del g._ctxs[ids[0]]; g._olvidar_relaciones(ids[0])
    assert all(not c.relaciones for c in g._ctxs.values())


def test_v4_estado_v3_sin_relaciones_sigue_cargando():
    g = _router_y_tv()
    d = g.to_dict()
    g2 = GestorContexto(); g2.from_dict(d)
    assert g2.relaciones() == [] and g2.resumen()["relaciones"] == []


def test_v4_titulos_sin_infinitivos_ni_gerundios():
    g = GestorContexto()
    assert g._es_verbal("llegar", "llega") and g._es_verbal("exponerte", "expon")
    assert not g._es_verbal("router", "route") and not g._es_verbal("mundo", "mundo")
    _correr(g, ["pero no es exponerte, es hacer que el mundo llegar a conocerte",
                "el mundo debería conocer el sistema"])


def test_v4_log_guarda_la_interseccion_y_mensajes_largos():
    import json
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "log.jsonl")
        g = GestorContexto(ruta_log=ruta)
        _correr(g, ["Estoy arreglando el router de Dark",
                    "El router devuelve la ruta equivocada para el clasificador",
                    "Quiero desarrollar el módulo de la TV",
                    "El módulo de la tele necesita el puerto del televisor",
                    "Vamos a definir los canales favoritos de la tele"])
        g.procesar("Vamos a usar el router para el módulo de la TV " + "palabra " * 30)
        filas = [json.loads(x) for x in open(ruta, encoding="utf-8")]
        assert filas[-1]["interseccion"][2] == "uso" and len(filas[-1]["texto"]) > 160


# --- V5 · nudos ---------------------------------------------------------------
_F_USO = "Vamos a usar el router para el módulo de la TV"
_F_AFECTA = "El error del router afecta al módulo de la tele"
_F_DEPENDE = "El módulo de la TV depende de las herramientas del router"


def _nivel_unico(g):
    rels = g.relaciones()
    assert len(rels) == 1, rels
    return rels[0]


def test_v5_varias_frases_seguidas_son_un_solo_episodio():
    g = _router_y_tv()
    for f in (_F_USO, _F_AFECTA, _F_DEPENDE):
        g.procesar(f)
    rel = _nivel_unico(g)
    assert rel["episodios"] == 1 and rel["nivel"] == "interseccion"


def test_v5_tres_episodios_forman_un_nudo_y_el_prompt_lo_comparte():
    g = _router_y_tv()
    nudo = None
    for f in (_F_USO, _F_AFECTA, _F_DEPENDE):
        g._turno += 20                                 # otro episodio
        r = g.procesar(f)
        nudo = nudo or r.nudo
    assert nudo and _nivel_unico(g)["nivel"] == "nudo"
    g.procesar("Bueno, volviendo al router...")
    assert "Contexto anudado" in g.bloque_prompt()


def test_v5_dos_episodios_con_dos_tipos_de_enlace_tambien_son_nudo():
    g = _router_y_tv()
    g.procesar(_F_USO)
    g._turno += 20
    g.procesar(_F_AFECTA)
    assert _nivel_unico(g)["nivel"] == "nudo"


def test_v5_dos_episodios_del_mismo_tipo_son_solo_vinculo():
    g = _router_y_tv()
    g.procesar(_F_USO)
    g._turno += 20
    g.procesar("Voy a usar el router para el puerto del televisor")
    assert _nivel_unico(g)["nivel"] == "vinculo"


def test_v5_sentido_solo_si_todas_las_frases_coinciden():
    g = _router_y_tv()
    for f in (_F_USO, _F_AFECTA, _F_DEPENDE):
        g._turno += 20
        g.procesar(f)
    de, hacia = _nivel_unico(g)["sentido"]
    titulos = {c.id: c.titulo.lower() for c in g._ctxs.values()}
    assert "rout" in titulos[de] and ("tv" in titulos[hacia] or "tele" in titulos[hacia])
    g2 = _router_y_tv()
    g2.procesar(_F_USO)
    g2._turno += 20
    g2.procesar("La tele afecta al error del router")       # sentido contrario
    assert _nivel_unico(g2)["sentido"] is None


def test_v5_el_nudo_sube_la_prioridad_y_el_interruptor_la_apaga():
    import nucleo.memoria.temas as m
    g = _router_y_tv()
    base = {c.id: g._prioridad(c) for c in g._ctxs.values()}
    for f in (_F_USO, _F_AFECTA):
        g._turno += 20
        g.procesar(f)
    c = g._ctxs[1]
    # el turno avanzó: comparo contra la misma prioridad sin la señal de relaciones
    con = g._prioridad(c)
    m.NUDOS_EN_PRIORIDAD = False
    try:
        sin = g._prioridad(c)
    finally:
        m.NUDOS_EN_PRIORIDAD = True
    assert con > sin and base


def test_v5_interruptor_del_prompt():
    import nucleo.memoria.temas as m
    g = _router_y_tv()
    g.procesar(_F_USO)
    g._turno += 20
    g.procesar(_F_AFECTA)
    g.procesar("Bueno, volviendo al router...")
    m.NUDOS_EN_PROMPT = False
    try:
        assert "Contexto anudado" not in g.bloque_prompt()
    finally:
        m.NUDOS_EN_PROMPT = True


def test_v5_un_tema_anudado_no_se_archiva_primero():
    g = _router_y_tv()
    g.procesar(_F_USO)
    g._turno += 20
    g.procesar(_F_AFECTA)
    ids = {c.id for c in g._ctxs.values()}
    for i in range(10, 14):
        c = g._nuevo_ctx(f"Tema suelto {i}"); c.id = i; c.estado = "secundario"
        c.turnos, c.ultimo_turno = 4, g._turno - 3
        g._ctxs[i] = c
    g._activo_id = 1
    g._aplicar_limite()
    assert all(g._ctxs[i].estado != "archivado" for i in ids)


def test_v5_relacion_guardada_por_v4_sigue_cargando():
    g = _router_y_tv()
    g.procesar(_F_USO)
    d = g.to_dict()
    for c in d["contextos"]:
        for rel in c["relaciones"].values():
            for k in ("episodios", "ultimo_ts", "sentidos"):
                rel.pop(k, None)
    g2 = GestorContexto(); g2.from_dict(d)
    assert _nivel_unico(g2)["nivel"] == "interseccion"
    g2._turno += 20
    g2.procesar(_F_AFECTA)
    assert _nivel_unico(g2)["nivel"] == "nudo"


def test_v5_reporte_resume_el_log():
    from nucleo.memoria import temas as m
    with tempfile.TemporaryDirectory() as d:
        ruta = os.path.join(d, "log.jsonl")
        g = GestorContexto(ruta_log=ruta)
        _correr(g, ["Estoy arreglando el router de Dark",
                    "El router devuelve la ruta equivocada para el clasificador",
                    "Quiero desarrollar el módulo de la TV",
                    "El módulo de la tele necesita el puerto del televisor",
                    "Vamos a definir los canales favoritos de la tele", _F_USO])
        txt = m.reporte(ruta)
        assert "INTERSECCIONES: 1" in txt and "turnos" in txt
    assert "no existe" in m.reporte(os.path.join(tempfile.gettempdir(), "no_existe_xyz.jsonl"))


# --- V6: separación y reconstrucción ----------------------------------------
class _Reloj:
    def __init__(self):
        self.t = 2_000_000.0

    def __call__(self):
        return self.t


_F_OTRO_USO = "Voy a usar el router para el puerto del televisor"
_SOLO_ROUTER = ["Revisar las rutas del router", "El router devuelve otra ruta mala del clasificador",
                "Corregir el clasificador del router", "Agregar logs a las rutas del router",
                "Probar el clasificador del router con más frases", "El router sigue con la ruta equivocada"]


def _nudo_con_reloj():
    clk = _Reloj()
    g = GestorContexto(reloj=clk)
    for f in ["Estoy arreglando el router de Dark",
              "El router devuelve la ruta equivocada para el clasificador",
              "Quiero desarrollar el módulo de la TV",
              "El módulo de la tele necesita el puerto del televisor",
              "Vamos a definir los canales favoritos de la tele"]:
        clk.t += 20
        g.procesar(f)
    for f in (_F_USO, _F_AFECTA, _F_DEPENDE):
        g._turno += 20
        clk.t += 20
        g.procesar(f)
    assert _nivel_unico(g)["nivel"] == "nudo"
    return g, clk


def _solos(g, clk, n):
    for i in range(n):
        clk.t += 20
        g.procesar(_SOLO_ROUTER[i % 6])


def test_v6_uso_independiente_afloja_pero_conserva_la_historia():
    g, clk = _nudo_con_reloj()
    antes = _nivel_unico(g)
    _solos(g, clk, 5)
    assert _nivel_unico(g)["tension"] == "apretado"
    _solos(g, clk, 12)
    d = _nivel_unico(g)
    assert d["tension"] == "flojo" and d["nivel"] == "nudo"
    assert d["evidencia"] == antes["evidencia"] and d["sentido"] == antes["sentido"]
    assert "Contexto anudado" not in g.bloque_prompt()


def test_v6_los_dias_sin_cruzarse_lo_duermen_y_un_cruce_lo_aprieta():
    g, clk = _nudo_con_reloj()
    clk.t += 4 * 86400
    assert _nivel_unico(g)["tension"] == "dormido"
    clk.t += 20
    r = g.procesar(_F_OTRO_USO)
    d = _nivel_unico(g)
    assert d["tension"] == "apretado" and d["nivel"] == "nudo" and r.reencuentro


def test_v6_una_negacion_sola_no_deshace_un_nudo_pero_tres_si_lo_aflojan():
    g, clk = _nudo_con_reloj()
    clk.t += 20
    r = g.procesar("El router no afecta al módulo de la TV")
    assert r.negacion and _nivel_unico(g)["tension"] == "apretado"
    for k, f in enumerate(["Los canales de la tele no dependen de las rutas del router",
                           "Las rutas del router no tienen nada que ver con los canales de la tele"]):
        clk.t += 20
        g.procesar("Seguimos con " + _SOLO_ROUTER[k])
        clk.t += 20
        g.procesar(f)
    d = _nivel_unico(g)
    assert d["tension"] != "apretado" and d["nivel"] == "nudo"


def test_v6_una_negacion_no_registra_una_relacion():
    g = _router_y_tv()
    r = g.procesar("El router no afecta al módulo de la TV")
    assert g.relaciones() == [] and not r.interseccion and not r.negacion
    g.procesar("No sé si el router afecta al módulo de la TV")   # duda: tampoco es negación
    assert not g.procesar("¿No afecta el router a la tele?").negacion


def test_v6_reencuentro_relajado_solo_con_historia_y_evidencia_suficiente():
    g, clk = _nudo_con_reloj()
    _solos(g, clk, 6)                         # el tema gana vocabulario propio
    clk.t += 4 * 86400
    clk.t += 20
    r = g.procesar("Las rutas del router y los canales de la tele")
    assert r.reencuentro and _nivel_unico(g)["tension"] == "apretado"
    assert "ya habían estado conectados" in g.bloque_prompt()
    # control: una pareja que NUNCA tuvo vínculo no se relaja
    g2 = _router_y_tv()
    r2 = g2.procesar("Las rutas del router y los canales de la tele")
    assert not r2.reencuentro


def test_v6_volver_a_un_tema_suelto_trae_su_relacion_anterior():
    g, clk = _nudo_con_reloj()
    clk.t += 3 * 86400
    clk.t += 20
    g.procesar("Volvamos al módulo de la TV")
    p = g.bloque_prompt()
    assert "Antes conectado con" in p and "No los mezcles" in p
    clk.t += 20
    g.procesar("Definir los canales de la tele otra vez")
    assert "Antes conectado con" not in g.bloque_prompt()      # solo el turno del regreso


def test_v6_prioridad_baja_si_el_nudo_esta_flojo_y_el_interruptor_la_devuelve():
    import nucleo.memoria.temas as m
    g, clk = _nudo_con_reloj()
    tv = max(g._ctxs.values(), key=lambda c: c.id)
    apretada = g._prioridad(tv)
    clk.t += 4 * 86400
    g._turno += 70
    floja = g._prioridad(tv)
    m.AFLOJAR_NUDOS = False
    try:
        assert g._tension(_nivel_unico_rel(g)) == "apretado"
    finally:
        m.AFLOJAR_NUDOS = True
    assert floja != apretada


def _nivel_unico_rel(g):
    c = next(iter(g._ctxs.values()))
    return next(iter(c.relaciones.values()))


def test_v6_estado_v5_sin_campos_nuevos_carga_y_el_roundtrip_conserva_todo():
    g, clk = _nudo_con_reloj()
    d = g.to_dict()
    assert d["version"] == 6
    for c in d["contextos"]:
        for rel in c["relaciones"].values():
            for k in ("solos", "neg_n", "neg_ts", "tension_vista"):
                rel.pop(k, None)
    g2 = GestorContexto(reloj=clk)
    g2.from_dict(d)
    assert _nivel_unico(g2)["nivel"] == "nudo"
    clk.t += 20
    g2.procesar(_F_USO)                       # no revienta con relaciones sin campos V6
    g3 = GestorContexto(reloj=clk)
    g3.from_dict(g2.to_dict())
    assert _nivel_unico(g3)["episodios"] == _nivel_unico(g2)["episodios"]


def test_v6_log_marca_aflojado_reencuentro_y_negacion():
    import json
    clk = _Reloj()
    ruta = os.path.join(tempfile.mkdtemp(), "log.jsonl")
    g, clk = _nudo_con_reloj()
    g._ruta_log = ruta
    _solos(g, clk, 17)
    clk.t += 20
    g.procesar("El router no afecta al módulo de la TV")
    clk.t += 20
    g.procesar(_F_OTRO_USO)
    filas = [json.loads(x) for x in open(ruta, encoding="utf-8")]
    assert any(f.get("aflojado") for f in filas)
    assert any(f.get("negacion") for f in filas)
    assert any(f.get("reencuentro") for f in filas)


def test_v6_el_limite_de_archivados_borra_primero_los_que_no_tienen_nudo():
    import nucleo.memoria.temas as m
    g, clk = _nudo_con_reloj()
    anud = [c for c in g._ctxs.values() if g._tiene_nudo(c)]
    for c in anud:
        c.estado = "archivado"
        c.ultimo_turno = -50                  # los más viejos
    for i in range(m.MAX_ARCHIVADOS):
        c = g._nuevo_ctx(f"relleno {i}")
        c.id = g._sig_id
        g._sig_id += 1
        c.estado = "archivado"
        c.ultimo_turno = i
        g._ctxs[c.id] = c
    g._aplicar_limite()
    assert all(c.id in g._ctxs for c in anud)


# --- V6.1: correcciones del log real ----------------------------------------
def _tema_cerebro():
    g = GestorContexto()
    _correr(g, [
        "Quiero entender cómo se almacena la información en el cerebro humano",
        "Y cómo hace el cerebro humano para guardar los recuerdos de la memoria",
        "La memoria del cerebro humano funciona con procesos químicos entre neuronas",
    ])
    assert g.resumen() is not None
    return g


def test_v61_un_relleno_no_hace_crecer_un_tentativo():
    # Caso del log: "ok, te me calmas. tranquilo" completaba la fuerza que le
    # faltaba a un tema en gestación y lo promovía sin aportar nada.
    from nucleo.memoria.temas import _norm, _stems
    g = GestorContexto()
    g.procesar("Quiero hablar de la serie del mentalista y sus personajes")
    t = g._tentativo
    assert t is not None
    f0 = t.fuerza
    for relleno in ("ok, te me calmas. tranquilo", "no quiero ninguna", "ok. a ver... ud"):
        n = _norm(relleno)
        r = g._reforzar_tentativo(t, relleno, n, _stems(n), 0.0)
        assert r.evento == DESVIO and t.fuerza == f0, (relleno, t.fuerza)
    n = _norm("la serie del mentalista tiene personajes buenos")   # esto sí es del tema
    g._reforzar_tentativo(t, "la serie del mentalista tiene personajes buenos", n, _stems(n), 0.5)
    assert t.fuerza > f0


def test_v61_una_raiz_que_choca_con_otra_palabra_no_hace_volver_a_un_tema():
    # "interesante" e "interrumpa" comparten las 5 letras ("inter"): en el log,
    # "hasta que lo interrumpa" devolvió a un tema que solo decía "interesante".
    g = GestorContexto()
    _correr(g, [
        "Quiero entender cómo se almacena la información en el cerebro humano",
        "Interesante, ¿puedes contarme más del cerebro humano y la memoria?",
        "La memoria del cerebro funciona con procesos químicos entre neuronas",
    ])
    g._enfriar()
    assert g.procesar("hasta que lo interrumpa").evento != REGRESO


def test_v61_el_regreso_implicito_con_evidencia_real_sigue_funcionando():
    g = _tema_cerebro()
    g._enfriar()
    r = g.procesar("Y los recuerdos del cerebro humano cómo se guardan")
    assert r.evento == REGRESO and "rebro" in r.titulo.lower()

def test_v61_regreso_por_contenido_entre_temas_pide_evidencia():
    g = _con_router_y_fisica()
    g.procesar("Sigo con el examen de física, la cinemática y los vectores")
    r = g.procesar("el router y las rutas de las herramientas fallan otra vez")
    assert r.evento == REGRESO and "outer" in r.titulo
    r = g.procesar("hay algo más que puedas hacer")
    assert r.evento != REGRESO


def test_v62_una_orden_externa_cuenta_como_turno_y_no_toca_temas():
    g = _tema_cerebro()
    n, antes = g.turno, len(g.contextos())
    r = g.registrar_accion("sube el volumen de la tele", origen="voz")
    assert g.turno == n + 1 and len(g.contextos()) == antes
    assert r.evento in (CONTINUA, DESVIO) and r.motivo.startswith("acción")
    # y no crea un tema en frío
    g2 = GestorContexto()
    g2.registrar_accion("abre chrome")
    assert g2.contextos() == []


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  OK   {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"  FALLA {nombre}: {e!r}")
                import traceback
                traceback.print_exc()
    print("\nTodo bien." if not fallos else f"\n{fallos} prueba(s) fallaron.")
    raise SystemExit(1 if fallos else 0)
