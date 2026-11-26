"""Contratos del subsistema de SITIOS WEB: puerto del almacén del usuario.

Este subsistema decide qué dirección se escribe en la barra del navegador
cuando el usuario pide una página. Hay tres capas de decisión, en el orden en que
`resolver_destino()` las consulta (K.3):

  1. lo que ya es una URL escrita por el usuario —se abre tal cual—;
  2. el almacén del usuario (`PuertoSitiosWeb`, este archivo): los sitios que él
     añadió desde la interfaz o por voz. Manda sobre la tabla porque es su
     palabra contra la nuestra;
  3. la tabla determinista de marcas, la capa 2 (el modelo propone un dominio y
     se comprueba que resuelve) y, si nada cierra, la búsqueda con la frase
     intacta.

Quien ejecuta la resolución es `nucleo/sitios_web.py` —ahí viven la tabla, la
política de URL, la fábrica y la fachada—. Este archivo solo fija qué puede
esperarse de un almacén, que es lo único que va a crecer con datos del usuario.

  PuertoSitiosWeb:
      * `sitio(nombre) -> Optional[str]`
            La URL guardada para ese nombre, o None. El nombre llega como lo dijo
            el usuario y SE NORMALIZA AQUÍ, dentro del almacén, con la misma
            `normalizar_destino()` con la que se escribió: comparar por otra
            cosa (sin acentos, sin el prefijo «la página de») sería otro idioma
            entre el que guarda y el que busca.
            No abre nada, no escribe, no lanza: si el fichero no está o no se
            entiende, devuelve None y la resolución sigue su camino.
      * `listar() -> List[dict]`
            Los sitios aprovechables, cada uno con `nombre` y `url`. Lo consume
            la interfaz (el panel de sitios del overlay, K.3.5) y cualquier diagnóstico.
            Las entradas sin nombre o con una URL que no pasa la política del
            punto 3 de K.3 NO salen por aquí: listar es enseñar lo que de verdad
            se puede abrir.
      * `guardar(nombre, url) -> Optional[str]`
            Escribe el sitio y devuelve la URL que quedó en disco, o None si no
            se guardó nada (nombre vacío, URL que no pasa la política). Aquí se
            valida AL ESCRIBIR con la misma `url_valida()` con la que se lee, así
            que el fichero no puede tener una entrada que luego no se pueda
            abrir. Un nombre que ya estaba se reemplaza en su sitio: el usuario
            corrigió la dirección, no pidió dos. Si el fichero no existe, se
            crea con su carpeta; si estaba roto, lo que se escriba lo reemplaza.
            La escritura es entera (fichero temporal y rename), nunca a medias.

            Lo que este puerto NO sabe es de quién viene la orden: la compuerta
            de que `sitio_web` solo se acepte desde loopback (K.3.5, requisito 4
            de K.3) es una decisión del transporte y vive en el despachador del
            Núcleo, porque el almacén no tiene conexión ni dirección remota que
            mirar. Un fallo de disco sí sube: quien llama lo registra.

  Quién lo construye: `nucleo/sitios_web.py:crear_almacen_sitios_web()` (la
  fábrica). El Núcleo lo pide con `_almacen_sitios_web()` en cada apertura y se lo
  pasa a `resolver_destino(almacen=...)`; si no le pasa ninguno, la resolución es
  exactamente la de K.3.2/K.3.3.

  La permanencia es deliberada: se lee el fichero en CADA consulta, sin caché en
  memoria. Lo que escribe la interfaz tiene que valer para el siguiente
  «abre X» sin reiniciar D.A.R.K., y un fichero de unos pocos sitios no justifica
  un invalidador. Lo que se cambia en disco se nota al vuelo; lo que se corrompe
  en disco se nota también, y como un fallo de lectura.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Protocol, runtime_checkable

__all__ = ["PuertoSitiosWeb"]


@runtime_checkable
class PuertoSitiosWeb(Protocol):
    """El almacén de los sitios que agregó el usuario."""

    def sitio(self, nombre: str) -> Optional[str]:
        """La URL guardada para este nombre, o None si no la hay."""
        ...

    def listar(self) -> List[Dict[str, str]]:
        """Los sitios aprovechables, con su nombre y su URL."""
        ...

    def guardar(self, nombre: str, url: str) -> Optional[str]:
        """Escribe el sitio y devuelve la URL que quedó en disco, o None."""
        ...
