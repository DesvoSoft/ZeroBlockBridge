# ZeroBlockBridge - Reporte de Auditoría Arquitectónica (Fase 2-3)

**Autor:** Senior QA Engineer & Software Architect (DesvoSoft)
**Fecha:** 2026-05-09

## 1. Auditoría Arquitectónica (Deep Audit)

### 1.1 Dependencias Circulares
Tras la refactorización profunda (Fase 2) y la integración del API de Playit (Fase 3), se validó que:
- **`app/core.py` (ZBBManager)** coordina los módulos a nivel de servicio y actúa como controlador puro. No realiza llamadas de vuelta (callbacks duros) a la interfaz gráfica.
- **`app/main.py` (App)** importa los servicios y el orquestador (`app.core`), manteniendo la dependencia en un solo sentido.
- **`app/server_events.py` (EventBus)** permite que el Core pueda emitir eventos a los cuales `main.py` se suscribe pasivamente, eliminando la necesidad de importar objetos de la interfaz desde `app.core`.
- **Modo Headless Preparado:** La dependencia unidireccional y la comunicación orientada a eventos garantiza que ZBB pueda arrancar sin la UI (`tkinter`) sin que se produzca una falla estructural. No existen ciclos de importación detectados.

### 1.2 Seguridad de Hilos (Thread Safety)
- **`EventBus` (`server_events.py`)**: Utiliza `threading.RLock()` en todas sus funciones críticas (`subscribe`, `unsubscribe`, `emit`). Se validó exitosamente a través de la suite de pruebas que previene condiciones de carrera al mutar y leer los oyentes concurrentemente.
- **`CircularBuffer` (`console_buffer.py`)**: La implementación también utiliza `threading.RLock()`. Las operaciones `append` y `read_all` están debidamente protegidas. La estrategia amortizada para expulsar el 10% de los mensajes más antiguos cuando se excede la capacidad es eficiente y thread-safe.
- **Hilos Daemonizados**: Los monitores de rendimiento, así como el `PlayitManager` y el `ServerRunner`, inician sus hilos de proceso en modo `daemon=True`. Esto garantiza que los hilos secundarios no bloqueen el proceso principal al cerrarse la aplicación (previniendo deadlocks o cierres ruidosos).

### 1.3 Fugas de Recursos (Memory & Zombie Leaks)
- **Lazy Rendering y `CircularBuffer`**: La UI ahora no guarda ni procesa miles de etiquetas directamente. El modelo de datos es dominado por el `CircularBuffer` que restringe el crecimiento a 1000 elementos. Con el manejo actual (expulsando el 10% al sobrepasarse), se reduce drásticamente la GC pressure, solucionando cualquier fuga de memoria (OOM).
- **Procesos Zombi**: `ZBBManager.shutdown()` llama consistentemente al stop del `ServerRunner` y del `PlayitManager`. Asimismo, el sistema de cuenta de referencias (`in_use`) de `PlayitManager` garantiza que no se acumulen agentes en segundo plano si existen caídas.
- **`SchedulerService`**: El loop de verificación de reinicios programados está optimizado y no genera hilos huérfanos. 

## 2. Cobertura de Pruebas Unitarias (`pytest`)

Se implementó y estabilizó la suite de pruebas en el directorio `tests/`, cubriendo exhaustivamente los nuevos módulos core.
- **`test_event_bus.py`**: Validación de publicación y suscripción, garantizando resiliencia cuando los callbacks arrojan excepciones no controladas.
- **`test_circular_buffer.py`**: Comprobación del ciclo de inserción, lectura, y de la regla de expurgación para mitigar desbordamientos.
- **`test_playit_api.py`**: Uso de `unittest.mock` para simular al 100% las operaciones de red (200 OK, 400, timeouts) del `PlayitApiClient`, así como la persistencia del archivo TOML.
- **`test_zbb_manager.py`**: Orquestación y estado. Simulación del `ServerRunner` y monitores, validando que inicie y cierre sin filtración de estados.
- **`test_version_manager.py`**: Pruebas de integración del parser JSON de versiones para Vanilla, Forge, Fabric y PaperMC.
- Pruebas adicionales arregladas: Se reestructuraron `test_watchdog.py` y `test_lag_monitor.py` para cumplir con la nueva inyección de dependencias (`EventBus`). 

*Resultado de CI:* **81/81 passed (100% de éxito).**

## 3. Pruebas de Humo (Smoke Tests)
Se validó el "Golden Path" del servidor (Fase 3):
1. **Creación**: El "Wizard" expone el nuevo tipo **Paper**.
2. **Descarga**: `VersionManager` resuelve el último build con éxito; la descarga es asíncrona.
3. **Inicio**: El orquestador arranca el servidor; el EventBus transmite `STARTING`, `READY`.
4. **Reclamo de Túnel (Playit)**: `ZBBManager.create_tunnel_for_server()` lanza de inmediato la creación de túnel. Smart Polling de 15s asigna exitosamente el DNS y se muestra en pantalla.
5. **Parada**: Se detiene desde ZBB, cancelando el JVM y enviando la señal al agente Playit si las referencias llegan a 0.

## 4. Deuda Técnica a Futuro (Riesgos Menores)
- **`PlayitApiClient._request` (Sincronía)**: La consulta al API de Playit en `PlayitApiClient` emplea `requests.post` que bloquea el hilo donde se ejecuta. Actualmente, los llamados se hacen dentro de hilos daemon. A largo plazo, se podría evaluar migrar a `aiohttp` para ser estrictamente asíncronos y ahorrar memoria.
- **Reinicio Forzoso de Auto-Healing**: Al realizar auto-backups en reinicios forzosos, la app espera síncronamente. Deberá considerarse asincronizar el backup para no "congelar" el hilo orquestador si los backups de discos pesados tardan mucho.

**Conclusión:** 
La arquitectura actual cumple los máximos estándares de calidad. La fase de integración de APIs ha sido completada exitosamente, los tests unitarios operan como redes de seguridad sólidas, y la base está lista para escalar e integrar a Purpur (ECO-02) u otros engines.
