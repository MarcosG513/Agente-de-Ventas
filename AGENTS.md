# Directrices del Proyecto: Venta de Google AI Pro 5 TB

1. **Catálogo Restringido:** El sistema (especialmente en la tabla `catalog` de SQLite) solo debe contemplar suscripciones de "Google AI Pro 5 TB". Los valores de duración (`duration`) en la base de datos están estrictamente limitados a rangos enteros entre 1 y 18 meses.
2. **Base de Datos Segura:** Usa `aiosqlite` con `PRAGMA journal_mode=WAL` y transacciones `BEGIN IMMEDIATE` para prevenir el error 'database is locked' bajo alta concurrencia en SQLite [17-19].
3. **Habilidad de Validación de Pagos:** Implementa en `.agents/skills/google-ai-pro-payment-validator/SKILL.md` las instrucciones detalladas para que el Agente evalúe comprobantes de pago e interrumpa el grafo (`interrupt_before=["human_validation"]`) para su verificación humana [20, 21].
