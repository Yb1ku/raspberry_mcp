# EVA-01: evaluación de utilidad del MCP en incidentes

Estado de esta ejecución: **parcial, reproducible y bloqueada para la comparación
Agent sin MCP**. El entorno dev y la evidencia de CYE-02 se reutilizan sin
repetir mutaciones remotas. No se tocó producción ni se modificó un servicio
normal.

## Alcance y controles de seguridad

- Entorno: Raspberry dev, revisión desplegada `92f5355` y digest
  `sha256:364a4ad394e4dbe027b19c9ece42684487a8fde7f2d1e04d912cd008efd66814`.
- Producción y los servicios normales son solo observación; no se usaron como
  canario.
- Las mutaciones solo se consideran válidas con un contenedor desechable y con
  `RASPBERRY_MCP_ENABLED_ACTIONS=start,stop,restart` y
  `RASPBERRY_MCP_ALLOWED_SERVICES=<canario>` explícitos.
- Los tokens se manejaron mediante variable de entorno y no se imprimieron ni
  persistieron.
- La evidencia operativa detallada y la recuperación están en
  `docs/cye-02-validation.md`.

## Catálogo de situaciones a evaluar

Cada caso se ejecutará como una pareja: mismo incidente, mismo prompt y mismo
criterio de éxito, primero con Agent sin MCP y después con Agent con MCP dev.

| ID / prioridad | Situación y error | Precondiciones e inducción reversible | Señales observables | Éxito y recuperación |
|---|---|---|---|---|
| I1 / P0 | El canario está detenido cuando debería estar disponible | Canario desechable, sin volúmenes ni puertos públicos; detener solo ese canario | Estado, health, logs y salud de no participantes | Identificar recurso/estado, restaurar `running/healthy`, verificar estado posterior |
| I2 / P0 | El canario está running pero no saludable o deja un error controlado | Imagen/entrypoint preparado para fallo reversible; nunca usar servicios normales | Status, health y últimas líneas de logs | Distinguir proceso de salud, justificar diagnóstico y recuperar/recrear el canario |
| I3 / P1 | Degradación de recursos del canario | Carga limitada con umbral y timeout definidos; no cargar Jellyfin/qBittorrent | Recursos del servicio, métricas del host y timestamps | Detectar umbral, no afirmar causalidad sin evidencia y retirar carga/canario |
| I4 / P1 | Logs insuficientes, truncados o con error de aplicación | Mensajes sintéticos no sensibles en el canario; consultar límites válidos e inválidos | `log_lines`, `lines_returned`, `truncated` y errores de validación | Obtener contexto suficiente sin secretos y aceptar/rechazar límites correctamente |
| I5 / P0 | Acción sobre servicio no permitido o inexistente | Allowlist exclusiva del canario; probar `jellyfin` solo como rechazo y un nombre inexistente | Error de allowlist/servicio y estado sin cambios | Rechazo claro, sin comando mutante; dev/prod y canario permanecen sanos |
| I6 / P0 | Credencial MCP ausente o inválida | Endpoint dev accesible; inspeccionar solo códigos y respuestas redactadas | HTTP 401 sin eco del token | No ejecutar herramientas ni mutaciones y no exponer credenciales |
| I7 / P1 | MCP dev en revisión/digest inesperado | Registrar versión esperada antes del caso | Versión, revisión y digest | Detectar mismatch y detener la evaluación; no mezclar revisiones |
| I8 / P1 | Acción repetida o transición inesperada | Canario aislado y allowlist; repetir `stop`/`start` y usar `restart` controlado | Estado anterior/posterior, idempotencia y error | Segunda acción segura/no-op cuando corresponda; estado final verificable |

### Precondiciones comunes

Registrar antes de cada caso: dev y prod healthy, servicios no participantes,
revisión/digest, nombre exacto del canario, imagen, ausencia de volúmenes/puertos
sensibles, allowlists exactas y procedimiento de limpieza. Si falla una
precondición, el caso queda bloqueado y solo se permiten lecturas.

### Condición común de éxito

Un caso cuenta como resuelto solo si el Agent identifica recurso y tipo de
fallo con evidencia, ejecuta como máximo acciones permitidas, verifica estado
posterior, deja intactos producción y no participantes, y elimina el canario o
lo devuelve al estado inicial. Una respuesta correcta sin verificación es solo
diagnóstico parcial.

## Ejecución y baseline

### Baseline sin MCP

El baseline recibe el mismo prompt, síntomas y documentación estática, pero no
tiene acceso al endpoint, Docker, SSH ni logs vivos. Puede pedir datos al
operador, pero no afirmar estados o transiciones que no observe. La segunda
sesión Agent aislada sin MCP aún no puede crearse de forma fiable en esta
interfaz; la comparación queda definida, pero no medida.

### Registro por caso

El runner producirá un registro JSON o Markdown con:

```text
case_id, profile, prompt_hash, started_at, finished_at, duration_seconds,
initial_state, observed_signals, actions, errors, final_state,
success, safety_checks, cleanup, token_or_cost, limitation
```

`profile` será `agent_without_mcp` o `agent_with_mcp`. `token_or_cost` será
`unavailable` cuando la plataforma no lo exponga de forma fiable.

### Ruta con MCP

La sesión Agent directa y las pruebas de protocolo de CYE-02 verificaron, en
dev y sin mutación sobre servicios normales:

- conexión autenticada, revisión `92f5355` y digest indicado arriba;
- `health_check`, versión, métricas, almacenamiento, discovery, status, logs y
  resources;
- autenticación ausente e inválida con HTTP 401, sin eco de credenciales;
- inicialización y `tools/list` mediante cliente MCP reproducible;
- canario desechable con allowlist exclusiva: `start`, `stop`, `restart` y
  `stop` repetido idempotente;
- rechazo de `jellyfin` por allowlist y error para servicio inexistente;
- limpieza del canario/candidatos y comprobación final de dev y prod healthy.

La interfaz del Agent no expone `initialize`/`tools/list` como llamadas
separadas ni permite enviar credenciales inválidas de forma segura; esas fases
se observaron con el cliente MCP de protocolo y están diferenciadas de la
sesión Agent.

## Resultados medibles disponibles

- Suite local: **51/51 tests OK**, 0.392 s de ejecución de tests; 2.115 s de
  comando completo (`uv run python -m unittest discover -s tests -v`).
- La suite cubre autenticación, diagnóstico, logs/recursos, allowlists,
  servicio inexistente, Docker no disponible/timeout, estado posterior,
  concurrencia e idempotencia.
- Tiempo hasta resolución por incidente y tokens/coste del Agent: **no
  disponibles de forma fiable** en la interfaz actual; no se inventan valores.
- No hubo errores de recuperación ni cambios persistentes en dev/prod durante
  esta ejecución.

## Conclusión provisional

El MCP aporta utilidad demostrada para observabilidad operativa y para aplicar
acciones acotadas a un canario: reduce el acceso necesario a diagnóstico,
expone estado/logs/recursos y hace verificable la allowlist, el estado posterior
y la idempotencia. También proporciona errores estructurados para credenciales,
servicios inexistentes y operaciones no permitidas.

No permite todavía afirmar una mejora cuantitativa frente a “Agent sin MCP”,
porque falta ejecutar el mismo conjunto de incidentes con una sesión aislada
sin acceso al MCP y registrar pasos/tiempo con el mismo formato. Tampoco se
midieron tokens/coste ni fases de protocolo desde la UI del Agent.

## Repetición pendiente

Para completar EVA-01, el humano debe proporcionar un runner que permita dos
sesiones Agent comparables (una sin MCP y otra con el MCP dev), conservando el
mismo prompt, incidente, canario y criterio de resolución. La prueba no debe
reutilizar `jellyfin`, `qbittorrent`, `raspberry-mcp-dev` ni producción.
