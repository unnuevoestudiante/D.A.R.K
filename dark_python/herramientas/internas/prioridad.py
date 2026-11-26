"""
dark_prioridad.py
Un reemplazo para threading.Lock() que sirve exactamente igual
(with lock: ..., lock.locked()), pero con una diferencia: si la llamada
viene del hilo de tareas de fondo, espera su turno cuando el usuario tiene
algo pendiente. Así una tarea larga (escribir_documento, replanificar...)
no bloquea tus comandos de voz durante todo su tiempo de ejecución, solo
entre llamadas individuales al modelo.

No resuelve la contención real de CPU (sigue siendo un solo modelo corriendo
a la vez, eso no cambia en hardware CPU-only), pero evita que una tarea de
fondo monopolice el lock llamada tras llamada sin dar ninguna oportunidad
al primer plano.

Uso: en vez de
    self._llm_lock = threading.Lock()
usa
    self._llm_lock = LockConPrioridad(hilo_bg_nombre="tareas_bg")

Y al crear el hilo de tareas de fondo, dale ese nombre:
    threading.Thread(target=self._worker_tareas_bg, daemon=True,
                      name="tareas_bg").start()

El resto del código (with self._llm_lock:, self._llm_lock.locked()) no
cambia en absoluto.
"""

import threading


class LockConPrioridad:
    def __init__(self, hilo_bg_nombre="tareas_bg", espera_maxima_s=0.3):
        self._lock = threading.Lock()
        self._cond = threading.Condition()
        self._prioritarios_esperando = 0
        self._hilo_bg_nombre = hilo_bg_nombre
        self._espera_maxima_s = espera_maxima_s

    def _es_hilo_bg(self):
        return threading.current_thread().name == self._hilo_bg_nombre

    def __enter__(self):
        if self._es_hilo_bg():
            # Antes de tomar el lock, si hay una petición del usuario
            # esperando, le cedemos el paso.
            with self._cond:
                while self._prioritarios_esperando > 0:
                    self._cond.wait(timeout=self._espera_maxima_s)
            self._lock.acquire()
        else:
            # Avisamos que hay una petición prioritaria ANTES de intentar
            # tomar el lock, para que el hilo de fondo la vea en su
            # próxima pausa entre llamadas.
            with self._cond:
                self._prioritarios_esperando += 1
            try:
                self._lock.acquire()
            finally:
                with self._cond:
                    self._prioritarios_esperando -= 1
                    self._cond.notify_all()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._lock.release()
        with self._cond:
            self._cond.notify_all()
        return False

    def acquire(self, *args, **kwargs):
        # Compatibilidad con código que llama .acquire()/.release() directo
        # en vez de "with". No aplica la prioridad en ese caso: úsalo solo
        # con "with" si quieres el beneficio.
        return self._lock.acquire(*args, **kwargs)

    def release(self):
        self._lock.release()

    def locked(self):
        return self._lock.locked()


if __name__ == "__main__":
    import time

    lock = LockConPrioridad(hilo_bg_nombre="tareas_bg")
    eventos = []

    def tarea_larga():
        for i in range(6):
            with lock:
                eventos.append(("bg_inicio", i, time.time()))
                time.sleep(0.3)  # simula una llamada al modelo
                eventos.append(("bg_fin", i, time.time()))

    def peticion_usuario():
        time.sleep(0.45)  # llega a mitad de la tarea de fondo
        t0 = time.time()
        with lock:
            eventos.append(("usuario_atendido", None, time.time() - t0))

    hilo_bg = threading.Thread(target=tarea_larga, name="tareas_bg")
    hilo_usuario = threading.Thread(target=peticion_usuario)
    hilo_bg.start()
    hilo_usuario.start()
    hilo_bg.join()
    hilo_usuario.join()

    espera_usuario = next(e[2] for e in eventos if e[0] == "usuario_atendido")
    print(f"El usuario esperó {espera_usuario:.2f}s (con 6 llamadas de "
          f"0.3s en fondo, sin prioridad habría esperado hasta ~1.8s)")
    for e in eventos:
        print(e)
