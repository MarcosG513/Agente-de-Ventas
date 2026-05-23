import asyncio
import aiosqlite

async def seed_catalog():
    sql = """
    BEGIN IMMEDIATE;

    -- Eliminamos la tabla anterior si existe para recargarla
    DROP TABLE IF EXISTS catalog;

    -- 1. Creación de la Tabla de Catálogo
    CREATE TABLE catalog (
        plan_id TEXT PRIMARY KEY, 
        plan_name TEXT DEFAULT 'Google AI Pro 5 TB',
        duration_months INTEGER CHECK(duration_months >= 1 AND duration_months <= 18), 
        price REAL, -- Los valores ahora representan PESOS
        features TEXT 
    );

    -- 2. Inserción de la Escalera de Valor en Pesos
    INSERT INTO catalog (plan_id, duration_months, price, features) VALUES
    ('g_ai_pro_5tb_1m', 1, 8000.00, '5TB Almacenamiento, Gemini Advanced. Facturación mensual regular.'),
    ('g_ai_pro_5tb_3m', 3, 21000.00, '5TB Almacenamiento, Gemini Advanced. (Equivale a 7,000 Pesos al mes)'),
    ('g_ai_pro_5tb_6m', 6, 36000.00, '5TB Almacenamiento, Gemini Advanced. Ahorro del 25% vs plan mensual.'),
    ('g_ai_pro_5tb_12m', 12, 50000.00, '5TB Almacenamiento, Gemini Advanced. Ahorro de casi el 50% (Mejor valor).'),
    ('g_ai_pro_5tb_18m', 18, 70000.00, '5TB Almacenamiento, Gemini Advanced. Máximo ahorro garantizado a largo plazo.');

    COMMIT;
    """
    
    # Cargamos a la base de datos principal de I/O
    async with aiosqlite.connect("ventas.db") as db:
        await db.executescript(sql)
        print("Catálogo de 'Google AI Pro 5 TB' (Pesos) inyectado exitosamente en ventas.db")

if __name__ == "__main__":
    asyncio.run(seed_catalog())
