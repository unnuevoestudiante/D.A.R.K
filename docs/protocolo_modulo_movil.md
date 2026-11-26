"""
docs/protocolo_modulo_movil.md

Especificación del Protocolo de Comunicación entre Núcleo/Hive y Dark Móvil (Android).
Puerto estándar: WebSocket 8766.
"""

# Protocolo Dark Móvil <-> Hive/Núcleo

## 1. Handshake y Autenticación

Al abrir la conexión WebSocket con `ws://<ip_nucleo>:8766`, el cliente móvil envía de inmediato el mensaje `hello`:

```json
{
  "type": "hello",
  "token": "<token_de_config/modulo_token.txt>",
  "module_id": "opcional_si_ya_lo_conoce_o_null",
  "device_key": "hardware_unique_id",
  "device": "Pixel 7 Pro",
  "module_type": "phone",
  "capabilities": ["say", "ask", "torch", "call", "open_app", "battery", "status", "ping"]
}
```

El servidor Hive responde con `welcome`:
```json
{
  "type": "welcome",
  "module_id": "a1b2c3d4e5f60718293a4b5c6d7e8f90",
  "name": "Teléfono 1",
  "number": 1,
  "module_type": "phone",
  "capabilities": ["..."],
  "new": false,
  "role": "module"
}
```

---

## 2. Petición del Teléfono al Núcleo (`core_request`)

Cuando el usuario hace una consulta que requiere el cerebro (LLM, memoria, búsqueda, abrir algo en el PC):

### A. Celular envía `core_request`:
```json
{
  "type": "core_request",
  "id": "e305e7ba-f538-4e1d-84ad-98114f243001",
  "text": "Abre Chrome en el PC y busca el informe de ventas",
  "timestamp": 1729984000000,
  "context": {
    "battery": 84,
    "charging": false,
    "in_call": false
  }
}
```

### B. Hive confirma recibo inmediato (`core_ack`):
*(Esto previene timeout y evita duplicaciones en la cola de reintentos).*
```json
{
  "type": "core_ack",
  "id": "e305e7ba-f538-4e1d-84ad-98114f243001"
}
```

### C. Núcleo procesa y responde (`core_response`):
```json
{
  "type": "core_response",
  "id": "e305e7ba-f538-4e1d-84ad-98114f243001",
  "ok": true,
  "text": "Listo, Chrome abierto con el informe."
}
```

---

## 3. Órdenes del Núcleo al Teléfono (`command`)

Cuando el Núcleo necesita que el teléfono actúe localmente (TTS, linterna, etc.):

```json
{
  "type": "command",
  "id": "cmd_7721",
  "action": "torch",
  "params": {
    "enable": true
  }
}
```

El teléfono ejecuta y responde con `result`:
```json
{
  "type": "result",
  "id": "cmd_7721",
  "ok": true,
  "text": "Linterna encendida"
}
```

---

## 4. Eventos de Presencia del Núcleo (`hub_event`)

Emitidos por el Coordinador Hive a todos los módulos:
- `{"type": "hub_event", "event": "core_online"}`: El PC Núcleo se ha conectado; el celular puede vaciar su `PendingQueue`.
- `{"type": "hub_event", "event": "core_offline"}`: El PC Núcleo se apagó o desconectó; el celular conmuta a modo respaldo y encola todo lo que no sea local.
