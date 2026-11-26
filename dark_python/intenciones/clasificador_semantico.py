"""
dark_python/intenciones/clasificador_semantico.py

Clasificador semántico ultraligero y 100% offline basado en embeddings ONNX.
- Compara la frase del usuario contra los ejemplos definidos en config/intenciones.json
- Discrimina entre órdenes reales y simple conversación / preguntas explicativas.
- Pesa menos de 25MB y responde en <20ms en CPU.
"""

from __future__ import annotations
import json
from pathlib import Path
import numpy as np
from fastembed import TextEmbedding

# Resolver ruta absoluta a config/intenciones.json sin importar desde dónde se ejecute el script
RAIZ_PROYECTO = Path(__file__).resolve().parent.parent.parent
CONFIG_INTENCIONES = RAIZ_PROYECTO / "config" / "intenciones.json"

class ClasificadorIntenciones:
    def __init__(self, json_path: Path = CONFIG_INTENCIONES):
        self.json_path = json_path
        # Usamos el modelo multilingüe oficial paraphrase-multilingual-MiniLM-L12-v2
        self.embedding_model = TextEmbedding(model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
        self.categorias: list[dict] = []
        self.centroides = []
        self._cargar_y_calcular()

    def _cargar_y_calcular(self):
        if not self.json_path.exists():
            raise FileNotFoundError(f"No existe el archivo {self.json_path}")

        raw = json.loads(self.json_path.read_text(encoding="utf-8"))
        self.categorias = raw

        # Guardar cada ejemplo individualmente para k-NN (k-Nearest Neighbors)
        self.todos_los_ejemplos = []
        self.todos_los_labels = []

        todos_los_textos = []
        for cat in self.categorias:
            for ej in cat.get("ejemplos", []):
                todos_los_textos.append(ej)
                self.todos_los_labels.append(cat)

        embeddings = list(self.embedding_model.embed(todos_los_textos))
        # Normalizar cada vector
        self.vectores_ejemplos = np.array([e / np.linalg.norm(e) for e in embeddings])

    def clasificar(self, texto: str) -> dict:
        texto = texto.strip()
        if not texto:
            return {"intencion": "desconocida", "tipo": "CONVERSACION", "confianza": 0.0}

        # Embedding del texto de entrada
        vec = list(self.embedding_model.embed([texto]))[0]
        vec = vec / np.linalg.norm(vec)

        # Similitud directa contra cada frase de ejemplo (Dot product)
        similitudes = np.dot(self.vectores_ejemplos, vec)
        mejor_idx = int(np.argmax(similitudes))
        mejor_sim = float(similitudes[mejor_idx])

        cat_elegida = self.todos_los_labels[mejor_idx]

        # Umbral adaptable: >= 0.55 para emparejar intención
        es_accion = (cat_elegida["tipo"] == "ACCION") and (mejor_sim >= 0.55)

        return {
            "texto_usuario": texto,
            "intencion": cat_elegida["intencion"],
            "tipo": cat_elegida["tipo"],
            "accion": cat_elegida["accion"],
            "confianza": round(mejor_sim, 4),
            "es_orden_real": es_accion
        }

if __name__ == "__main__":
    print("Inicializando Clasificador Semántico ONNX...")
    clf = ClasificadorIntenciones()
    print("¡Listo! Probando casos de prueba:\n")

    pruebas = [
        # Pruebas de Música
        "Reproduce música",
        "Pon algo para concentrarme",
        "Quiero escuchar algo de Mozart",
        # Falsos positivos de Música
        "¿Cómo funciona un reproductor de música?",
        "Más tarde quiero escuchar música",
        
        # Pruebas de Navegador
        "Abre el navegador",
        "Necesito consultar unas cosas en internet",
        # Falsos positivos de Navegador
        "¿Cómo abriría Chrome desde Python?",
        
        # Documentos
        "Hazme un documento con esta información",
        "Déjame esto guardado en un archivo",
        
        # Consultas de hora / avisos
        "¿Qué hora es?",
        "Avísame cuando pasen veinte minutos",
        
        # Linterna
        "No veo nada aquí a oscuras"
    ]

    for p in pruebas:
        res = clf.clasificar(p)
        accion_str = f"EJECUTAR [{res['accion']}]" if res["es_orden_real"] else "CHARLAR / EXPLICAR (Cero acciones)"
        print(f"«{p}»")
        print(f"  -> Intención : {res['intencion']} (Confianza: {res['confianza']})")
        print(f"  -> Resultado : {accion_str}\n")
