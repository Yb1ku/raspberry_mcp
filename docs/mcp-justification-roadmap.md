# Qué tendría que aportar el MCP para justificar su uso

## Resumen ejecutivo

La evaluación de EVA-01 mostró que el MCP actual no añade una capacidad
operativa clara cuando el Agent ya dispone de terminal, SSH y Docker. El Agent
puede consultar los mismos datos y ejecutar las mismas acciones directamente.
Además, el perfil con terminal consumió menos tokens que el perfil MCP en las
pruebas realizadas.

El MCP se justificaría como una frontera operacional segura y semántica, no
como una segunda forma de ejecutar `docker ps`, `docker logs` o `docker
restart`. Para que exista una diferencia real, el MCP debe aportar al menos una
de estas propiedades:

1. acceso controlado cuando el Agent no tiene terminal ni SSH;
2. capacidades de diagnóstico y recuperación que no estén disponibles como
   comandos genéricos;
3. enforcement técnico de políticas que el Agent no pueda saltarse;
4. operaciones compuestas con precondiciones, confirmación, rollback y
   verificación integrados;
5. identidad, auditoría y descubrimiento seguros entre dispositivos.

## Situación actual

El servidor actual ofrece herramientas de observabilidad y lifecycle control:

- health, versión, métricas y almacenamiento;
- discovery de contenedores;
- status, logs y recursos de servicios;
- `start`, `stop` y `restart` con allowlist e idempotencia.

Estas herramientas son útiles como contrato de API, pero su capacidad se
solapa con el acceso directo a Docker. En EVA-01 se observó lo siguiente:

- el Agent con terminal pudo inspeccionar los mismos estados, logs y procesos;
- pudo localizar un proceso `yes` consumiendo CPU;
- pudo eliminar el marcador que provocaba un healthcheck unhealthy;
- pudo reiniciar y arrancar el contenedor directamente;
- pudo consultar autenticación y metadatos de imagen con `curl` y Docker;
- el MCP consumió más tokens brutos en la configuración evaluada.

La allowlist del MCP sí aporta una garantía técnica que Docker directo no
aplica por sí mismo. Sin embargo, esa ventaja desaparece si el Agent conserva
acceso equivalente al socket Docker o a SSH con permisos suficientes.

## Principio de diseño

El Agent debe poder resolver incidentes operativos sin recibir acceso general a
la máquina. El MCP debe exponer intenciones operativas limitadas y verificables
en lugar de exponer primitivas de infraestructura.

La frontera deseada sería:

```text
Agent
  -> intención operacional y contexto del incidente
MCP
  -> autenticación, autorización, preflight, ejecución, verificación y auditoría
Raspberry
  -> Docker, sistema operativo, métricas, logs y despliegues
```

El Agent no debería necesitar conocer el socket Docker, nombres internos de
contenedores, comandos shell, rutas del host ni credenciales de infraestructura.

## Capacidades que justificarían el MCP

### 1. Acceso remoto sin terminal

El MCP debe funcionar desde un Agent que no tenga SSH, Docker ni terminal local.
Esto es especialmente importante para un Agent ejecutándose en un móvil, en
otro ordenador o en un entorno restringido.

Debe incluir:

- descubrimiento de la Raspberry en la red autorizada;
- identidad verificable de cada Raspberry;
- emparejamiento explícito con confirmación humana;
- adaptación a cambios de IP mediante mDNS, DNS-SD o un registro seguro;
- autenticación sin copiar tokens en prompts o archivos de configuración;
- errores diferenciados para Pi apagada, MCP no disponible, credencial inválida
  y pérdida de red;
- posibilidad de revocar una Raspberry emparejada.

El criterio de éxito sería que el Agent pueda resolver un incidente desde un
dispositivo sin terminal y sin que el usuario ejecute comandos manuales.

### 2. Diagnóstico compuesto de incidentes

Las herramientas actuales devuelven piezas separadas. Una herramienta de
diagnóstico útil debería correlacionarlas:

```text
diagnose_incident(
  target="jellyfin",
  symptom="unhealthy",
  window_minutes=15,
  detail="standard"
)
```

La respuesta debería incluir:

- identidad del host y revisión/digest desplegado;
- estado del servicio y healthcheck;
- cambios recientes y hora del último despliegue;
- logs relevantes, ya filtrados y redactados;
- métricas de CPU, memoria, red y disco;
- dependencias afectadas;
- comparación con un baseline saludable;
- hipótesis ordenadas por evidencia;
- acciones sugeridas y nivel de riesgo;
- campos explícitos de incertidumbre.

El valor añadido sería reducir varias llamadas y permitir razonamiento sobre una
ventana temporal coherente. El Agent no tendría que descubrir por sí mismo qué
consultas combinar ni cómo correlacionar timestamps.

### 3. Plan seguro antes de modificar

Antes de ejecutar una acción mutable, el MCP debería ofrecer un plan verificable:

```text
plan_recovery(
  target="jellyfin",
  incident_id="...",
  proposed_action="restart",
  mode="safe"
)
```

El plan debería indicar:

- qué recurso exacto se afectará;
- por qué la acción está autorizada;
- estado actual y estado esperado;
- impacto previsto;
- precondiciones;
- acciones que no se ejecutarán;
- estrategia de rollback;
- comprobaciones posteriores;
- necesidad de confirmación humana.

El plan debe soportar `dry_run=true` y producir una huella estable que pueda
auditarse antes y después de la ejecución.

### 4. Recuperación semántica y verificable

En lugar de exponer únicamente `start_service`, `stop_service` y
`restart_service`, el MCP debería ofrecer operaciones con objetivos de estado:

```text
ensure_service_healthy(
  target="jellyfin",
  max_duration_seconds=60,
  allow_restart=true
)
```

La herramienta debería:

1. comprobar identidad y allowlist;
2. capturar el estado inicial;
3. decidir si la acción es necesaria;
4. ejecutar el mínimo cambio permitido;
5. verificar el healthcheck y las dependencias;
6. detenerse ante una transición inesperada;
7. revertir cuando sea seguro;
8. devolver estado inicial, acciones, estado final y evidencia.

El resultado no debe ser simplemente “restart OK”. Debe demostrar que el
servicio alcanzó el estado operacional solicitado.

### 5. Rollback y gestión de despliegues

El MCP podría aportar una capacidad que Docker directo no tiene de forma segura
por defecto: operar sobre artefactos inmutables y recuperar una versión conocida.

Herramientas posibles:

- `get_deployment_provenance`;
- `compare_deployed_revision`;
- `list_promotable_digests`;
- `rollback_to_known_good`;
- `promote_tested_digest`.

Cada operación debería exigir:

- digest exacto, no solo una etiqueta mutable;
- historial de despliegue;
- comprobación de que la imagen fue validada en dev;
- autorización separada para dev y producción;
- confirmación humana para producción;
- registro de actor, motivo y resultado;
- rollback documentado y verificable.

Esto convertiría al MCP en una interfaz de operaciones de despliegue, no en un
envoltorio de comandos Docker.

### 6. Seguridad técnica y least privilege

El MCP debe ser la única vía disponible para el Agent. Si el Agent conserva
SSH, Docker socket o un shell con permisos equivalentes, la allowlist deja de
ser una frontera fiable.

La implementación debería incluir:

- proceso MCP separado del Agent;
- usuario sin privilegios de host;
- ausencia de Docker socket directo para el Agent;
- socket proxy con endpoints mínimos si el servidor necesita Docker;
- allowlist deny-by-default;
- permisos separados por herramienta y servicio;
- autorización por recurso, entorno y tipo de acción;
- expiración y rotación de credenciales;
- rate limits y timeouts;
- bloqueo de argumentos shell, Docker flags y rutas arbitrarias;
- validación de nombres y referencias contra inventario autorizado;
- redacción de tokens, variables de entorno y secretos en errores y logs.

Debe existir una prueba negativa que demuestre que un Agent conectado al MCP no
puede convertir una herramienta de servicio en ejecución arbitraria de comandos.

### 7. Auditoría y trazabilidad

Cada llamada relevante debería producir un evento auditable con:

- actor y sesión;
- Raspberry y entorno;
- herramienta y versión del contrato;
- recurso objetivo;
- motivo o incidente asociado;
- estado anterior y posterior;
- autorización aplicada;
- aprobación humana, si existió;
- timestamps;
- resultado y error sanitizado;
- digest/revisión del servidor.

La auditoría no debe incluir tokens, cuerpos completos de logs sensibles ni
variables de entorno.

### 8. Contratos de datos útiles para el Agent

Las respuestas deben ser estables, pequeñas y orientadas a decisiones. Cada
respuesta mutable debería incluir al menos:

```json
{
  "operation_id": "...",
  "target": "eva01-canary",
  "environment": "dev",
  "server_revision": "...",
  "previous_state": {"status": "running", "health": "healthy"},
  "requested_transition": "restart",
  "actions_taken": ["restart"],
  "resulting_state": {"status": "running", "health": "healthy"},
  "verified": true,
  "rollback_available": true,
  "errors": []
}
```

Los errores deben distinguir autorización, validación, inexistencia,
incapacidad del backend, timeout, healthcheck fallido y rollback incompleto.

### 9. Automatización de incidentes recurrentes

El MCP podría encapsular runbooks aprobados para incidentes conocidos:

- servicio unhealthy;
- disco lleno;
- crecimiento anómalo de logs;
- contenedor reiniciando;
- despliegue en revisión equivocada;
- dependencia no disponible;
- certificado próximo a caducar.

Cada runbook debe ser versionado, tener límites de impacto y permitir solo las
acciones expresamente aprobadas. El Agent debe poder pedir un runbook por
identificador y recibir el plan antes de ejecutarlo.

### 10. Capacidad de diagnóstico sin datos sensibles

El MCP debería entregar evidencia suficiente para resolver incidentes sin
exponer información que el Agent no necesita:

- filtrado de logs por patrón y ventana temporal;
- redacción de tokens, cookies, rutas privadas y datos personales;
- resumen de errores con enlaces a eventos auditables;
- exclusión de variables de entorno;
- límites de tamaño y paginación;
- separación entre datos operativos y secretos.

El éxito sería que el Agent pueda identificar la causa de un incidente sin
recibir el log bruto completo.

## Cambios concretos en la API

Una primera versión justificable podría añadir estas herramientas:

| Herramienta | Aporta frente a terminal directo | Requisito de seguridad |
|---|---|---|
| `discover_hosts` | Identidad y disponibilidad de Raspberry autorizadas | No escaneo indiscriminado; emparejamiento explícito |
| `get_incident_snapshot` | Correlación de estado, logs, recursos y versión | Redacción y límites de datos |
| `plan_recovery` | Preflight y dry-run con impacto previsto | No mutar; huella del plan |
| `execute_recovery` | Ejecución limitada con aprobación y rollback | Allowlist, estado previo/posterior y auditoría |
| `ensure_service_healthy` | Objetivo semántico con verificación | Timeout, límites y rollback |
| `get_deployment_provenance` | Relación entre host, digest y revisión | Solo artefactos inmutables |
| `rollback_to_known_good` | Recuperación de una versión validada | Confirmación y permiso por entorno |
| `get_audit_event` | Explicación de acciones y decisiones | Sin secretos en auditoría |

## Criterios de aceptación

El MCP justificaría su uso si una nueva evaluación demuestra todos estos puntos:

### Acceso

- El Agent resuelve casos desde un entorno sin SSH, Docker ni terminal.
- Puede descubrir y seleccionar la Raspberry correcta con identidad verificable.
- La autenticación no requiere pegar tokens en el prompt.

### Capacidad

- El Agent resuelve al menos tres incidentes que no pueda resolver desde el
  mismo entorno sin MCP.
- Al menos una resolución exige correlacionar varias fuentes de datos.
- Al menos una recuperación exige rollback o verificación compuesta.

### Seguridad

- Una llamada sobre un servicio no permitido es rechazada técnicamente.
- No existe una herramienta que acepte shell, Docker flags o rutas arbitrarias.
- El Agent no puede acceder al Docker socket por otra vía.
- Cada mutación produce auditoría y estado anterior/posterior.

### Eficiencia

- Se comparan tokens de entrada, salida y coste con prompts idénticos.
- Se mide tiempo hasta diagnóstico y tiempo hasta recuperación.
- Se cuentan llamadas, reintentos, errores y mensajes de coordinación.
- Se separa el coste fijo del catálogo MCP del coste específico del incidente.

El MCP no debería considerarse justificado solo por tener una tasa de éxito
similar a SSH/Docker. Debe aportar seguridad, disponibilidad, semántica o
automatización que el perfil terminal no tenga.

## Nueva evaluación recomendada

La siguiente versión de EVA-01 debería utilizar tres condiciones:

1. Agent sin MCP ni terminal;
2. Agent con terminal, SSH y Docker;
3. Agent con MCP, sin SSH, Docker ni terminal.

El tercer perfil es el decisivo. Cada caso debe usar el mismo incidente y el
mismo canario, con prompts equivalentes y orden aleatorizado. Debe medirse:

- éxito de diagnóstico;
- éxito de recuperación;
- tiempo hasta primera hipótesis;
- tiempo hasta estado sano;
- número de pasos;
- llamadas de herramientas;
- tokens de entrada y salida;
- coste;
- errores y reintentos;
- cambios realizados;
- incidentes de seguridad.

La hipótesis que se quiere demostrar es que el MCP permite resolver de forma
segura un incidente que el Agent puede resolver con terminal, pero que no puede
resolver en el perfil sin terminal. La segunda hipótesis es que lo hace con una
superficie de permisos menor y una trazabilidad mejor.

## Orden de implementación recomendado

### P0

- Eliminar acceso equivalente a SSH/Docker del perfil MCP de evaluación.
- Implementar `get_incident_snapshot` con correlación de datos y redacción.
- Implementar `plan_recovery` con dry-run, precondiciones y riesgo.
- Mantener allowlists deny-by-default y permisos por entorno.
- Registrar auditoría de cada llamada y transición.

### P1

- Implementar `execute_recovery` con aprobación, idempotencia, estado posterior
  y rollback.
- Añadir identidad y descubrimiento seguro de Raspberry.
- Añadir provenance de despliegue y validación de digest.
- Añadir runbooks versionados para incidentes recurrentes.

### P2

- Correlación histórica y baselines automáticos.
- Gestión multi-host.
- Optimización de respuestas y paginación para reducir tokens.
- Métricas de coste integradas en los resultados de evaluación.

## Conclusión

El MCP actual es una interfaz útil y más segura que Docker directo cuando el
Agent no tiene otro acceso privilegiado. En el experimento realizado, sin
embargo, el Agent sí tenía terminal y por eso la capacidad funcional quedó casi
igualada.

La dirección correcta no es añadir más wrappers de Docker. Es retirar el acceso
directo del perfil MCP, elevar el nivel semántico de las herramientas, integrar
preflight/rollback/auditoría y demostrar que el Agent puede resolver incidentes
desde un entorno donde el terminal no está disponible.
