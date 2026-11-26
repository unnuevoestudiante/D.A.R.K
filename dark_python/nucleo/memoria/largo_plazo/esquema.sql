CREATE TABLE contextos (
  uid TEXT PRIMARY KEY,
  nombre TEXT NOT NULL,
  creado TEXT NOT NULL,
  dispositivo TEXT NOT NULL,
  rev INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE nodos (
  uid TEXT PRIMARY KEY,
  tipo TEXT NOT NULL,              -- persona, proyecto, tema, hecho, preferencia, objeto, lugar, evento, tema_web
  nombre TEXT NOT NULL,
  resumen TEXT,                    -- el dato, en palabras de Dark
  contexto_uid TEXT REFERENCES contextos(uid),
  origen TEXT NOT NULL CHECK (origen IN ('usuario','inferido','web')),
  peso REAL NOT NULL,
  vigencia TEXT NOT NULL CHECK (vigencia IN ('estable','decae','volatil')),
  vida_media_dias REAL,            -- solo 'decae'
  vence_en TEXT,                   -- solo 'volatil'
  estado TEXT NOT NULL DEFAULT 'vigente'
         CHECK (estado IN ('vigente','historico','pendiente_conflicto')),
  clave_canonica TEXT NOT NULL,    -- tipo|nombre_normalizado|contexto_uid
  creado TEXT NOT NULL,
  actualizado TEXT NOT NULL,
  ultimo_uso TEXT,
  dispositivo TEXT NOT NULL,
  rev INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_nodos_clave ON nodos(clave_canonica) WHERE estado = 'vigente';

CREATE TABLE aristas (
  uid TEXT PRIMARY KEY,
  de_uid TEXT NOT NULL REFERENCES nodos(uid),
  a_uid  TEXT NOT NULL REFERENCES nodos(uid),
  relacion TEXT NOT NULL,          -- parte_de, relacionado_con, contradice, ...
  peso REAL NOT NULL DEFAULT 0.5,
  actualizado TEXT NOT NULL,
  dispositivo TEXT NOT NULL,
  rev INTEGER NOT NULL DEFAULT 1
);
CREATE UNIQUE INDEX ux_aristas ON aristas(de_uid, a_uid, relacion);

CREATE TABLE nodos_historial (
  uid TEXT PRIMARY KEY,
  nodo_uid TEXT NOT NULL REFERENCES nodos(uid),
  resumen TEXT,
  reemplazado_en TEXT NOT NULL,
  motivo TEXT                      -- actualizacion, contradiccion_resuelta
);

CREATE TABLE conflictos (
  uid TEXT PRIMARY KEY,
  nodo_a_uid TEXT NOT NULL REFERENCES nodos(uid),
  nodo_b_uid TEXT NOT NULL REFERENCES nodos(uid),
  detectado_en TEXT NOT NULL,
  resuelto_en TEXT,
  ganador_uid TEXT REFERENCES nodos(uid)
);

CREATE TABLE conocimiento_web (
  uid TEXT PRIMARY KEY,
  nodo_uid TEXT NOT NULL REFERENCES nodos(uid),
  fuente_nombre TEXT,
  fuente_url TEXT,
  consultado_en TEXT NOT NULL
);

CREATE TABLE cola_extraccion (
  uid TEXT PRIMARY KEY,
  dispositivo TEXT NOT NULL,
  contexto_uid TEXT,
  texto TEXT NOT NULL,             -- segmento de conversación
  creado TEXT NOT NULL,
  estado TEXT NOT NULL DEFAULT 'pendiente'
         CHECK (estado IN ('pendiente','procesando','hecho','fallido')),
  intentos INTEGER NOT NULL DEFAULT 0
);

-- Sincronización
CREATE TABLE cambios (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  uid TEXT NOT NULL, tabla TEXT NOT NULL,
  operacion TEXT NOT NULL CHECK (operacion IN ('crear','editar','borrar')),
  ts TEXT NOT NULL, dispositivo TEXT NOT NULL
);
CREATE TABLE lapidas (uid TEXT PRIMARY KEY, tabla TEXT NOT NULL, borrado_en TEXT NOT NULL);
CREATE TABLE alias_uid (uid_alias TEXT PRIMARY KEY, uid_canonico TEXT NOT NULL);
CREATE TABLE sync_estado (dispositivo TEXT PRIMARY KEY, ultimo_seq_visto INTEGER NOT NULL);

CREATE VIRTUAL TABLE nodos_fts USING fts5(nombre, resumen, content='nodos', content_rowid='rowid');