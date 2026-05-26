import os
import uuid
from dotenv import load_dotenv

load_dotenv()
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base, Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime, ForeignKey, Boolean, CheckConstraint, Index, event

# Configuración de base de datos unificada
db_path = os.getenv("DB_PATH", "ventas.db")
DATABASE_URL = f"sqlite+aiosqlite:///{db_path}"

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
)

# 1. Configuración de Conexión (PRAGMAs Avanzados)
@event.listens_for(engine.sync_engine, "connect")
def do_connect(dbapi_connection, connection_record):
    # Deshabilitar transacción implícita para usar BEGIN IMMEDIATE
    if hasattr(dbapi_connection, "isolation_level"):
        dbapi_connection.isolation_level = None
        
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")           # Concurrencia segura
    cursor.execute("PRAGMA synchronous=NORMAL")         # Seguro vs corrupción y rápido
    cursor.execute("PRAGMA busy_timeout=60000")         # Espera de 60s si hay bloqueos
    cursor.execute("PRAGMA temp_store=MEMORY")          # Temporales en RAM
    cursor.close()

# Consideración Arquitectónica Crítica (Transacciones)
@event.listens_for(engine.sync_engine, "begin")
def do_begin(conn):
    # Envolver forzosamente las escrituras en BEGIN IMMEDIATE
    conn.exec_driver_sql("BEGIN IMMEDIATE")

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

Base = declarative_base()

# 2. Esquemas de Tablas (Data Models)

class Cliente(Base):
    """1. Clientes y seguimiento del embudo"""
    __tablename__ = "clientes"
    
    telefono: Mapped[str] = mapped_column(String, primary_key=True)
    estado: Mapped[str] = mapped_column(String, server_default='bot_activo', default='bot_activo')
    es_nuevo: Mapped[bool] = mapped_column(Boolean, server_default='1', default=True)
    last_phone_id: Mapped[str] = mapped_column(String, nullable=True)
    email: Mapped[str] = mapped_column(String, nullable=True)

# Índice explícito solicitado para el teléfono del cliente
Index('idx_clientes_telefono', Cliente.telefono)


class Catalog(Base):
    """2. Catálogo Restringido a Google AI Pro 5 TB"""
    __tablename__ = "catalog"
    
    plan_id: Mapped[str] = mapped_column(String, primary_key=True) # Ej: 'g_ai_pro_5tb_1m'
    plan_name: Mapped[str] = mapped_column(String, server_default='Google AI Pro 5 TB')
    duration_months: Mapped[int] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float, nullable=True)
    features: Mapped[str] = mapped_column(String, nullable=True)
    
    # Restricción de negocio inmutable
    __table_args__ = (
        CheckConstraint('duration_months >= 1 AND duration_months <= 18', name='check_duration_months'),
    )


class Subscription(Base):
    """3. Control de Suscripciones"""
    __tablename__ = "subscriptions"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(ForeignKey("clientes.telefono"), nullable=True)
    plan_id: Mapped[str] = mapped_column(ForeignKey("catalog.plan_id"), nullable=True)
    start_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    end_date: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, server_default='0', default=False)


class PaymentProof(Base):
    """4. Auditoría de Pagos y protocolo HITL"""
    __tablename__ = "payment_proofs"
    
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    customer_id: Mapped[str] = mapped_column(ForeignKey("clientes.telefono"), nullable=True)
    media_id: Mapped[str] = mapped_column(String, nullable=True) # ID del archivo en WhatsApp
    amount_paid: Mapped[str] = mapped_column(String, nullable=True) # Extraído por visión como String
    transaction_date: Mapped[str] = mapped_column(String, nullable=True) # Extraído por visión como String
    reference_number: Mapped[str] = mapped_column(String, nullable=True) # Extraído por visión
    bank_name: Mapped[str] = mapped_column(String, nullable=True) # Nombre del banco
    confirmed_by_human: Mapped[bool] = mapped_column(Boolean, server_default='0', default=False)


# Funciones I/O Asíncronas
async def obtener_o_crear_cliente(telefono: str) -> Cliente:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(Cliente).where(Cliente.telefono == telefono)
            result = await session.execute(stmt)
            cliente = result.scalar_one_or_none()
            if not cliente:
                cliente = Cliente(telefono=telefono, estado='bot_activo', es_nuevo=True)
                session.add(cliente)
            return cliente

async def actualizar_estado_cliente(telefono: str, nuevo_estado: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(Cliente).where(Cliente.telefono == telefono)
            result = await session.execute(stmt)
            cliente = result.scalar_one_or_none()
            if cliente:
                cliente.estado = nuevo_estado

async def obtener_planes_catalogo():
    async with AsyncSessionLocal() as session:
        stmt = select(Catalog).order_by(Catalog.duration_months.asc())
        result = await session.execute(stmt)
        return result.scalars().all()

async def registrar_comprobante_pago(customer_id: str, media_id: str, monto: str, fecha: str, referencia: str, banco: str = None):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            proof = PaymentProof(
                customer_id=customer_id,
                media_id=media_id,
                amount_paid=monto,
                transaction_date=fecha,
                reference_number=referencia,
                bank_name=banco,
                confirmed_by_human=False
            )
            session.add(proof)

async def actualizar_last_phone_id(telefono: str, last_phone_id: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(Cliente).where(Cliente.telefono == telefono)
            result = await session.execute(stmt)
            cliente = result.scalar_one_or_none()
            if cliente:
                cliente.last_phone_id = last_phone_id

async def guardar_email_cliente(telefono: str, email: str):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = select(Cliente).where(Cliente.telefono == telefono)
            result = await session.execute(stmt)
            cliente = result.scalar_one_or_none()
            if cliente:
                cliente.email = email

# Inicializador del modelo en DB
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        
        # Intentar agregar la columna last_phone_id por compatibilidad con bases de datos ya creadas
        from sqlalchemy import text
        try:
            await conn.execute(text("ALTER TABLE clientes ADD COLUMN last_phone_id TEXT"))
        except Exception:
            pass
            
        # Intentar agregar la columna email por compatibilidad con bases de datos ya creadas
        try:
            await conn.execute(text("ALTER TABLE clientes ADD COLUMN email TEXT"))
        except Exception:
            pass
