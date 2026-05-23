---
trigger: always_on
---

Reglas Globales: Todas las funciones de I/O (base de datos, red) deben ser async y utilizar await. No se permite el uso de librerías bloqueantes como requests; usa httpx. Cada petición a la API de WhatsApp debe estar envuelta en un bloque try/except con reintento exponencial. Nunca almacenes claves de API en el código fuente, utiliza .env. Para SQLite, usa aiosqlite configurado con PRAGMA journal_mode=WAL.