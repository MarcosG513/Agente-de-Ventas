import os
import hmac
import hashlib
import json
import httpx
import sys
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables del entorno
load_dotenv()

from fastapi import FastAPI, Request, Response, HTTPException, BackgroundTasks, Header, Query
from fastapi.responses import HTMLResponse
from agent_graph import get_compiled_graph
from langchain_core.messages import HumanMessage, AIMessage
from database import init_db, AsyncSessionLocal, Catalog, obtener_o_crear_cliente, actualizar_estado_cliente
from sqlalchemy import select

# Inicializar FastAPI
app = FastAPI(title="Matelu Digital - API Omnicanal")

# Configuración mediante variables de entorno
GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY", "")
WHATSAPP_PHONE_ID = os.environ.get("WHATSAPP_PHONE_ID", "")
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN", "")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN", "IA_matelu_2026")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.environ.get("ADMIN_CHAT_ID", "")
APP_SECRET = os.environ.get("META_APP_SECRET", "")

# Configuración de base de datos e historial para persistencia
DB_PATH = os.environ.get("DB_PATH", "ventas.db")
db_dir = os.path.dirname(DB_PATH)
HISTORIAL_PATH = os.path.join(db_dir, "historial.db") if db_dir else "historial.db"

# Función auxiliar para imprimir de forma segura en consolas con codificaciones limitadas (como Windows CP1252)
def safe_print(message: str):
    try:
        print(message)
    except UnicodeEncodeError:
        try:
            # Reintentar codificando en ascii reemplazando caracteres desconocidos
            print(message.encode(sys.stdout.encoding or 'ascii', errors='replace').decode(sys.stdout.encoding or 'ascii'))
        except Exception:
            # Fallback definitivo a ignorar errores
            print(message.encode('ascii', errors='replace').decode('ascii'))

# --- EVENTOS DE INICIALIZACIÓN ---
@app.on_event("startup")
async def startup_event():
    await init_db()
    async with AsyncSessionLocal() as session:
        # Precargar datos de prueba si está vacío
        stmt = select(Catalog)
        result = await session.execute(stmt)
        if not result.scalars().first():
            safe_print("Precargando catálogo de Google AI Pro...")
            session.add_all([
                Catalog(plan_id="g_ai_pro_5tb_1m", plan_name="Google AI Pro 5 TB", duration_months=1, price=8000.0, features="5TB Almacenamiento, Gemini Advanced. Facturación mensual regular."),
                Catalog(plan_id="g_ai_pro_5tb_3m", plan_name="Google AI Pro 5 TB", duration_months=3, price=21000.0, features="5TB Almacenamiento, Gemini Advanced. (Equivale a 7,000 Pesos al mes)"),
                Catalog(plan_id="g_ai_pro_5tb_6m", plan_name="Google AI Pro 5 TB", duration_months=6, price=36000.0, features="5TB Almacenamiento, Gemini Advanced. Ahorro del 25% vs plan mensual."),
                Catalog(plan_id="g_ai_pro_5tb_12m", plan_name="Google AI Pro 5 TB", duration_months=12, price=50000.0, features="5TB Almacenamiento, Gemini Advanced. Ahorro de casi el 50% (Mejor valor)."),
                Catalog(plan_id="g_ai_pro_5tb_18m", plan_name="Google AI Pro 5 TB", duration_months=18, price=70000.0, features="5TB Almacenamiento, Gemini Advanced. Máximo ahorro garantizado a largo plazo.")
            ])
            await session.commit()

# --- CEREBRO ÚNICO ---
async def procesar_inteligencia_agente(texto_usuario: str, nombre_usuario: str, plataforma: str) -> str:
    """
    Cerebro único que centraliza la lógica de procesamiento con el modelo y flujo de agentes.
    Conecta directamente con la invocación de LangGraph/Gemini y utiliza el checkpointer de SQLite WAL.
    """
    safe_print(f">>> [CEREBRO ÚNICO] Procesando mensaje en plataforma: {plataforma}")
    safe_print(f"    Usuario (ID): {nombre_usuario} | Texto: {texto_usuario}")
    
    try:
        # 1. Verificar si el cliente está en modo silencio
        cliente = await obtener_o_crear_cliente(nombre_usuario)
        if cliente.estado in ['esperando_humano', 'pausado']:
            safe_print(f"Modo Silencio: Cliente {nombre_usuario} en estado '{cliente.estado}'. Abortando procesamiento.")
            return ""

        # 2. Conexión segura a SQLite para LangGraph checkpointer
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        
        async with aiosqlite.connect(HISTORIAL_PATH, isolation_level=None) as conn:
            async with conn.cursor() as cursor:
                await cursor.execute("PRAGMA journal_mode=WAL")
                await cursor.execute("PRAGMA synchronous=NORMAL")
                await cursor.execute("PRAGMA busy_timeout=60000")
                await cursor.execute("PRAGMA temp_store=MEMORY")
            
            memory = AsyncSqliteSaver(conn)
            await memory.setup()
            graph = get_compiled_graph(memory)
            
            config = {"configurable": {"thread_id": nombre_usuario}}
            
            # Inicializar o actualizar el estado del agente
            state_update = {
                "phone_number": nombre_usuario,
                "audio_media_id": None,
                "image_media_id": None,
                "messages": [HumanMessage(content=texto_usuario)]
            }
            
            # Invocar al agente de LangGraph
            final_state = await graph.ainvoke(state_update, config=config)
            
            # Extraer la respuesta generada por el LLM
            messages_out = final_state.get("messages", [])
            if messages_out:
                last_msg = messages_out[-1]
                if isinstance(last_msg, AIMessage) and last_msg.content:
                    return last_msg.content
            
            return "Dame un momento, estoy actualizando mi base de datos de licencias en este instante."

    except Exception as e:
        safe_print(f"Error en procesar_inteligencia_agente: {str(e)}")
        return "Dame un momento, estoy actualizando mi base de datos de licencias en este instante."

# --- LÓGICA ANTERIOR DE LANGGRAPH (PRESERVADA PARA REFERENCIA/USO FUTURO) ---
def verify_meta_signature(payload: bytes, signature_header: str):
    """
    Valida la integridad del request mediante la verificación del hash HMAC provisto en el encabezado.
    """
    if not signature_header:
        raise HTTPException(status_code=400, detail="El encabezado X-Hub-Signature-256 es requerido")
    
    parts = signature_header.split("=")
    if len(parts) != 2 or parts[0] != "sha256":
        raise HTTPException(status_code=400, detail="Formato de firma no válido")
        
    signature = parts[1]
    
    expected_signature = hmac.new(
        APP_SECRET.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    if not hmac.compare_digest(expected_signature, signature):
        raise HTTPException(status_code=403, detail="Firma de Meta rechazada")

# --- INTEGRACIÓN DE TELEGRAM ---
async def enviar_alerta_auditoria(chat_id_cliente: str, nombre_cliente: str, file_id: str):
    """
    Envía una alerta al grupo de auditoría (ADMIN_CHAT_ID) con la foto del comprobante,
    un pre-análisis de Gemini Vision y dos botones inline interactivos para Aprobar o Rechazar el pago.
    """
    if not TELEGRAM_BOT_TOKEN or not ADMIN_CHAT_ID:
        safe_print(">>> [AUDITORÍA] Error: TELEGRAM_BOT_TOKEN o ADMIN_CHAT_ID no configurados.")
        return

    # Pre-análisis de la imagen con Gemini Vision
    respuesta_gemini = "Error al pre-analizar la imagen"
    
    try:
        # TAREA 2: Descargar la imagen de Telegram
        # 1. Obtener file_path
        get_file_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getFile?file_id={file_id}"
        async with httpx.AsyncClient() as client:
            res_file = await client.get(get_file_url, timeout=10.0)
            res_file.raise_for_status()
            file_data = res_file.json()
            file_path = file_data.get("result", {}).get("file_path")
            
        if file_path:
            # 2. Descargar bytes de la imagen
            download_url = f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}"
            async with httpx.AsyncClient() as client:
                res_img = await client.get(download_url, timeout=15.0)
                res_img.raise_for_status()
                img_bytes = res_img.content
                
            # TAREA 3: PIPELINE DE COMPRESIÓN DE IMÁGENES
            from PIL import Image
            import io
            
            try:
                img = Image.open(io.BytesIO(img_bytes))
                img = img.convert("RGB")
                img.thumbnail((800, 800))
                out = io.BytesIO()
                img.save(out, format="JPEG", quality=60)
                compressed_bytes = out.getvalue()
                safe_print(f">>> [AUDITORÍA] Imagen comprimida con PIL. De {len(img_bytes)} a {len(compressed_bytes)} bytes.")
                image_data = compressed_bytes
            except Exception as pil_err:
                safe_print(f">>> [AUDITORÍA] Error al comprimir imagen con PIL (usando original): {pil_err}")
                image_data = img_bytes

            # TAREA 3: Análisis con Gemini Vision usando google-generativeai
            import google.generativeai as genai
            genai.configure(api_key=GOOGLE_API_KEY)
            
            # Instanciar el modelo gemini-2.5-flash
            model = genai.GenerativeModel("gemini-2.5-flash")
            
            # Pasar bytes y prompt
            prompt = f"Actúa como auditor financiero de Matelu Store. Hoy es {datetime.now().strftime('%d de %B de %Y')}. Analiza esta imagen. ¿Es un comprobante válido de transferencia bancaria (Nequi, Bancolombia, etc.)? Responde de forma ultra concisa (máximo 2 líneas). Usa la fecha de hoy que te acabo de dar para evaluar lógicamente cualquier fecha en la imagen. Si la fecha de la imagen es anterior o igual a hoy, es válida."
            
            image_part = {
                "mime_type": "image/jpeg",
                "data": image_data
            }
            
            # Llamar a Gemini Vision asíncronamente
            response = await model.generate_content_async([prompt, image_part])
            respuesta_gemini = response.text.strip()
            safe_print(f">>> [AUDITORÍA] Pre-análisis de Gemini exitoso: {respuesta_gemini}")
            
    except Exception as e:
        safe_print(f">>> [AUDITORÍA] Fallo pre-análisis de Gemini/Telegram (procediendo con fallback): {e}")
        respuesta_gemini = "Error al pre-analizar la imagen"

    # TAREA 4: Enviar alerta con la foto y los botones inline
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    
    reply_markup = {
        "inline_keyboard": [
            [
                {"text": "✅ Aprobar", "callback_data": f"aprobar_{chat_id_cliente}"},
                {"text": "❌ Rechazar", "callback_data": f"rechazar_{chat_id_cliente}"}
            ]
        ]
    }
    
    caption_text = (
        f"🚨 NUEVO COMPROBANTE RECIBIDO\n"
        f"Cliente: {nombre_cliente}\n\n"
        f"🤖 Análisis IA: {respuesta_gemini}\n\n"
        f"Esperando tu revisión final..."
    )
    
    payload = {
        "chat_id": ADMIN_CHAT_ID,
        "photo": file_id,
        "caption": caption_text,
        "reply_markup": reply_markup
    }
    
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=15.0)
            if res.status_code == 200:
                safe_print(f">>> [AUDITORÍA] Alerta enviada correctamente a administrador para cliente {nombre_cliente}.")
            else:
                safe_print(f">>> [AUDITORÍA] Error de API ({res.status_code}): {res.text}")
    except Exception as e:
        safe_print(f">>> [AUDITORÍA] Excepción al intentar enviar alerta al administrador: {e}")

def detectar_intencion_humano(texto: str) -> bool:
    palabras_clave = ["asesor", "persona", "hablar con alguien"]
    texto_lower = texto.lower()
    return any(p in texto_lower for p in palabras_clave)

async def obtener_historial_y_resumir(chat_id: str) -> str:
    try:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        
        async with aiosqlite.connect(HISTORIAL_PATH, isolation_level=None) as conn:
            memory = AsyncSqliteSaver(conn)
            await memory.setup()
            graph = get_compiled_graph(memory)
            config = {"configurable": {"thread_id": chat_id}}
            state = await graph.aget_state(config)
            
            messages = state.values.get("messages", []) if state and state.values else []
            
            if not messages:
                return "El cliente solicitó soporte directo sin historial previo."
                
            # Formatear el historial para el LLM
            historial_formateado = ""
            for msg in messages:
                from langchain_core.messages import HumanMessage
                role = "Cliente" if isinstance(msg, HumanMessage) else "Bot"
                historial_formateado += f"{role}: {msg.content}\n"
                
            # Llamar a Gemini para resumir
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm_resumidor = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.3)
            prompt = (
                f"Analiza la siguiente conversación de soporte y genera un resumen conciso "
                f"explicando qué plan estaba mirando el cliente o cuál es su duda exacta:\n\n"
                f"{historial_formateado}\n"
                f"Responde de forma ultra concisa (máximo 3 líneas)."
            )
            response = await llm_resumidor.ainvoke([HumanMessage(content=prompt)])
            return response.content.strip()
    except Exception as e:
        safe_print(f"Error al generar resumen del historial: {e}")
        return "No se pudo recuperar el historial de la conversación."

async def send_telegram_message(chat_id: str, texto: str):
    """
    Envía un mensaje de texto de vuelta al usuario en Telegram utilizando el bot token configurado.
    """
    if not TELEGRAM_BOT_TOKEN:
        safe_print(">>> [TELEGRAM] Error: TELEGRAM_BOT_TOKEN no configurado en el entorno.")
        return
        
    # Saneamiento de Markdown: en Telegram Markdown clásico (V1), bold se representa con * y no con **
    saneado = texto.replace("**", "*")
        
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": saneado,
        "parse_mode": "Markdown"
    }
    
    # Envío asíncrono con httpx con bloque try/except robusto y fallback para errores de formateo
    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(url, json=payload, timeout=10.0)
            try:
                res.raise_for_status()
                safe_print(f">>> [TELEGRAM] Mensaje enviado correctamente a chat_id: {chat_id}")
            except httpx.HTTPStatusError as http_err:
                if http_err.response.status_code == 400:
                    safe_print(f">>> [TELEGRAM] Fallback a texto plano activado por error 400 (Markdown inválido) en chat_id: {chat_id}")
                    # Enviar sin parse_mode
                    payload_fallback = {
                        "chat_id": chat_id,
                        "text": saneado
                    }
                    res_fb = await client.post(url, json=payload_fallback, timeout=10.0)
                    res_fb.raise_for_status()
                    safe_print(f">>> [TELEGRAM] Mensaje enviado correctamente usando fallback de texto plano a chat_id: {chat_id}")
                else:
                    raise http_err
    except Exception as e:
        safe_print(f">>> [TELEGRAM] Excepción al intentar enviar mensaje a chat_id {chat_id}: {e}")

@app.post("/webhook/telegram")
async def receive_telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook para recibir actualizaciones de Telegram.
    Extrae la información relevante, la procesa en el Cerebro Único y responde asíncronamente.
    Retorna siempre HTTP 200 (status: ok) para cumplir las directrices de estabilidad.
    """
    safe_print(">>> [TELEGRAM WEBHOOK] POST /webhook/telegram recibido!")
    try:
        payload = await request.json()
        
        # 1. Detectar Callback Query (Clics de botones del Administrador)
        if "callback_query" in payload:
            callback_query = payload["callback_query"]
            callback_query_id = callback_query.get("id")
            data = callback_query.get("data", "")
            
            message = callback_query.get("message", {})
            chat_id_admin = message.get("chat", {}).get("id")
            message_id = message.get("message_id")
            
            if data and "_" in data:
                action, chat_id_cliente = data.split("_", 1)
                
                async def procesar_callback():
                    try:
                        # Responder al cliente
                        if action == "aprobar":
                            await send_telegram_message(chat_id_cliente, "✅ Tu pago ha sido aprobado. En breve recibirás tu licencia.")
                        elif action == "rechazar":
                            await send_telegram_message(chat_id_cliente, "❌ Tu comprobante no es válido o es ilegible. Por favor, envíalo de nuevo.")
                            
                        # Confirmar el click al administrador
                        answer_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery"
                        answer_payload = {
                            "callback_query_id": callback_query_id,
                            "text": "Auditoría procesada."
                        }
                        async with httpx.AsyncClient() as client:
                            await client.post(answer_url, json=answer_payload, timeout=10.0)
                            
                        # Editar el mensaje original para remover botones y marcar como auditado
                        edit_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/editMessageCaption"
                        edit_payload = {
                            "chat_id": chat_id_admin,
                            "message_id": message_id,
                            "caption": f"🚨 NUEVO COMPROBANTE RECIBIDO\nCliente: {chat_id_cliente}\n[AUDITADO]",
                            "reply_markup": {"inline_keyboard": []}
                        }
                        async with httpx.AsyncClient() as client:
                            await client.post(edit_url, json=edit_payload, timeout=10.0)
                            
                    except Exception as ex:
                        safe_print(f"Error procesando callback de Telegram: {ex}")
                        
                background_tasks.add_task(procesar_callback)
            return {"status": "ok"}
            
        # 2. Procesamiento de Mensajes normales
        message = payload.get("message", {})
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        
        user_text = None
        file_id = None
        
        if "text" in message:
            user_text = message.get("text", "")
            
            # Interceptar comandos de control del Admin
            if str(chat_id) == str(ADMIN_CHAT_ID):
                if user_text.strip().startswith("/reanudar"):
                    parts = user_text.strip().split(" ")
                    if len(parts) > 1:
                        target_user_id = parts[1].strip()
                        await actualizar_estado_cliente(target_user_id, 'bot_activo')
                        await send_telegram_message(str(ADMIN_CHAT_ID), f"✅ Asistente de IA reactivado para el cliente {target_user_id}.")
                        await send_telegram_message(target_user_id, "🤖 El asistente de IA ha vuelto a activarse. ¿En qué más puedo ayudarte?")
                    else:
                        await send_telegram_message(str(ADMIN_CHAT_ID), "⚠️ Formato incorrecto. Usa: /reanudar <user_id>")
                    return {"status": "ok"}
                    
                elif user_text.strip().startswith("/pausar"):
                    parts = user_text.strip().split(" ")
                    if len(parts) > 1:
                        target_user_id = parts[1].strip()
                        await actualizar_estado_cliente(target_user_id, 'pausado')
                        await send_telegram_message(str(ADMIN_CHAT_ID), f"✅ Asistente de IA pausado para el cliente {target_user_id}. Modo manual activo.")
                        await send_telegram_message(target_user_id, "Comprendo perfectamente. Voy a transferirte con Marcos, nuestro especialista, para que te asista de forma personalizada. Dame un momento...")
                    else:
                        await send_telegram_message(str(ADMIN_CHAT_ID), "⚠️ Formato incorrecto. Usa: /pausar <user_id>")
                    return {"status": "ok"}
        elif "photo" in message or "document" in message:
            caption = message.get("caption", "").strip()
            if caption:
                user_text = f"[Imagen enviada] {caption}"
            else:
                user_text = "[El usuario ha enviado un archivo o imagen]"
                
            # Extraer file_id de mayor resolución si es foto
            if "photo" in message and message.get("photo"):
                file_id = message["photo"][-1].get("file_id")
        
        if chat_id and user_text is not None:
            # Función asíncrona interna para ejecutar en segundo plano y no bloquear la respuesta HTTP
            async def procesar_y_responder():
                try:
                    # 1. Cargar el cliente
                    cliente = await obtener_o_crear_cliente(str(chat_id))
                    
                    # 2. Si es el Administrador y está respondiendo a una alerta o mensaje del cliente
                    if str(chat_id) == str(ADMIN_CHAT_ID):
                        replied_message = message.get("reply_to_message", {})
                        replied_text = replied_message.get("text", "") or replied_message.get("caption", "")
                        if replied_text:
                            target_client_id = None
                            import re
                            if "🚨 ALERTA DE INTERVENCIÓN 🚨" in replied_text:
                                match = re.search(r"👤 Cliente:.*\((\d+)\)", replied_text)
                                if match:
                                    target_client_id = match.group(1)
                            elif "💬 Mensaje de Cliente" in replied_text:
                                match = re.search(r"💬 Mensaje de Cliente \((\d+)\)", replied_text)
                                if match:
                                    target_client_id = match.group(1)
                                    
                            if target_client_id:
                                await send_telegram_message(target_client_id, user_text)
                                await send_telegram_message(str(ADMIN_CHAT_ID), f"✅ Mensaje enviado al cliente {target_client_id}.")
                                return
                    
                    # 3. Silenciar si está pausado o esperando humano
                    if cliente.estado in ['esperando_humano', 'pausado'] and str(chat_id) != str(ADMIN_CHAT_ID):
                        safe_print(f"Modo Silencio/Pausado: Cliente {chat_id} en estado '{cliente.estado}'. Redireccionando mensaje al administrador.")
                        
                        # Enviar el mensaje del cliente al administrador
                        admin_forward_text = f"💬 Mensaje de Cliente ({chat_id}):\n{user_text}"
                        await send_telegram_message(str(ADMIN_CHAT_ID), admin_forward_text)
                        
                        # Si envió foto, podemos seguir auditando (enviar al admin)
                        if file_id:
                            from_user = message.get("from", {})
                            first_name = from_user.get("first_name", "Usuario")
                            await enviar_alerta_auditoria(str(chat_id), first_name, file_id)
                        return

                    # 4. Detección de intención de soporte humano
                    if detectar_intencion_humano(user_text) and str(chat_id) != str(ADMIN_CHAT_ID):
                        # Cambiar estado a 'pausado'
                        await actualizar_estado_cliente(str(chat_id), 'pausado')
                        
                        # Mensaje de transición al cliente
                        await send_telegram_message(str(chat_id), "Comprendo perfectamente. Voy a transferirte con Marcos, nuestro especialista, para que te asista de forma personalizada. Dame un momento...")
                        
                        # Generar resumen del historial
                        from_user = message.get("from", {})
                        first_name = from_user.get("first_name", "")
                        resumen_contexto = await obtener_historial_y_resumir(str(chat_id))
                        
                        # Enviar alerta al admin
                        nombre_formateado = f"{first_name} ({chat_id})" if first_name else f"Cliente ({chat_id})"
                        alerta_text = (
                            f"🚨 ALERTA DE INTERVENCIÓN 🚨\n"
                            f"👤 Cliente: {nombre_formateado}\n"
                            f"📝 Contexto: {resumen_contexto}"
                        )
                        await send_telegram_message(str(ADMIN_CHAT_ID), alerta_text)
                        return
                    
                    # 5. Manejo normal de /start y otros mensajes
                    if user_text.strip().startswith("/start"):
                        # Analizar argumentos de deep link
                        parts = user_text.strip().split(" ", 1)
                        param = parts[1].strip() if len(parts) > 1 else ""
                        
                        confirmacion = ""
                        if param:
                            plan_readable = ""
                            if "1_mes" in param:
                                plan_readable = "1 Mes"
                            elif "1_ano" in param or "1_ano" in param:
                                plan_readable = "1 Año"
                            elif "3_meses" in param:
                                plan_readable = "3 Meses"
                            elif "6_meses" in param:
                                plan_readable = "6 Meses"
                            elif "18_meses" in param:
                                plan_readable = "18 Meses"
                            else:
                                plan_readable = "nuestro plan Pro"
                            
                            confirmacion = f"¡Excelente! Veo que te interesa el plan de {plan_readable} de IA Pro. 🚀\n\n"
                        
                        welcome_text = f"""{confirmacion}🚀 ¡Hola! Bienvenido a Matelu Digital.
¿Listo para potenciar tu productividad y creatividad con Ingeniería de Inteligencia Artificial Avanzada?

🌟 NUESTRAS SUSCRIPCIONES GOOGLE AI PRO (5 TB):

• 🥉 1 Mes: 8,000 Pesos
• 🥈 3 Meses: 21,000 Pesos
• 🥇 6 Meses: 36,000 Pesos
• 🏆 1 Año: 50,000 Pesos (Mejor Valor)
• 💎 18 Meses: 70,000 Pesos (Ahorro Máximo)

💡 ¿Por qué dar el salto al plan Pro con nosotros?
✅ Almacenamiento masivo (5 TB / 5000 GB): Un almacén digital familiar masivo, listo para usar y compartible con hasta 5 personas.
✅ Memoria de genio (1M tokens): Capacidad drástica de contexto. Tu IA puede leer, analizar y recordar un libro entero de 700 páginas o códigos de programación completos en una sola charla.
✅ IA de Asistente a Colega de Trabajo: Integración total nativa dentro de tu Gmail, Docs, Sheets y Vids. Además, incluye el agente autónomo Daily Brief para organizar tu bandeja de entrada y calendario cada mañana.
✅ Estudio de Creación Profesional: Acceso a herramientas creativas de última generación para generar videos profesionales desde cero (Veo), componer imágenes fotorrealistas y análisis avanzado en NotebookLM (hasta 300 fuentes).

👉 ¿Con cuál de estos planes te gustaría empezar a trabajar sin límites hoy?"""
                        
                        await send_telegram_message(str(chat_id), welcome_text)
                    else:
                        # Usamos chat_id como identificador único de hilo/cliente
                        respuesta = await procesar_inteligencia_agente(user_text, str(chat_id), "telegram")
                        if respuesta:
                            await send_telegram_message(chat_id, respuesta)
                        
                    # Si se recibió foto, enviar alerta al grupo de auditoría
                    if file_id:
                        from_user = message.get("from", {})
                        first_name = from_user.get("first_name", "Usuario")
                        await enviar_alerta_auditoria(str(chat_id), first_name, file_id)
                except Exception as ex:
                    safe_print(f"Error procesando/enviando mensaje en Telegram background: {ex}")
            
            background_tasks.add_task(procesar_y_responder)
        else:
            safe_print(">>> [TELEGRAM WEBHOOK] Mensaje omitido (faltan datos: chat_id o texto/multimedia)")
            
    except Exception as e:
        safe_print(f">>> [TELEGRAM WEBHOOK] Error general procesando webhook: {e}")
        
    return {"status": "ok"}


# --- INTEGRACIÓN DE WHATSAPP (META) ---
@app.get("/webhook/whatsapp")
async def verify_whatsapp_webhook(
    mode: str = Query(None, alias="hub.mode"),
    token: str = Query(None, alias="hub.verify_token"),
    challenge: str = Query(None, alias="hub.challenge")
):
    """
    Validación exigida por Meta para registrar el webhook de WhatsApp Cloud API.
    """
    safe_print(">>> [WHATSAPP WEBHOOK] GET /webhook/whatsapp de verificación recibido")
    if mode == "subscribe" and token == VERIFY_TOKEN:
        safe_print(">>> [WHATSAPP WEBHOOK] Validación exitosa del token.")
        return Response(content=challenge, status_code=200)
    safe_print(">>> [WHATSAPP WEBHOOK] Fallo en la verificación del token.")
    raise HTTPException(status_code=403, detail="Fallo en la verificación del token de webhook")

@app.post("/webhook/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_hub_signature_256: str = Header(None)
):
    """
    Recibe los payloads de mensajes entrantes desde la API Cloud de WhatsApp.
    Parsea el JSON anidado, extrae el número y texto del remitente, e invoca al Cerebro Único.
    Retorna siempre HTTP 200 (status: ok).
    """
    safe_print(">>> [WHATSAPP WEBHOOK] POST /webhook/whatsapp recibido!")
    raw_body = await request.body()
    
    # Validación HMAC si se configuró APP_SECRET
    if APP_SECRET:
        try:
            verify_meta_signature(raw_body, x_hub_signature_256)
        except HTTPException as he:
            raise he
        except Exception as e:
            safe_print(f">>> [WHATSAPP WEBHOOK] Error validando firma HMAC: {e}")
            raise HTTPException(status_code=403, detail="Firma inválida")

    try:
        data = json.loads(raw_body)
        
        # Parsing de la estructura anidada de Meta
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                messages = value.get("messages", [])
                
                for msg in messages:
                    phone_number = msg.get("from")
                    if not phone_number:
                        continue
                        
                    msg_type = msg.get("type")
                    text_body = ""
                    
                    if msg_type == "text":
                        text_body = msg.get("text", {}).get("body", "")
                    elif msg_type == "image":
                        text_body = "[Envié un comprobante de pago o imagen]"
                    elif msg_type == "audio":
                        text_body = "[Audio Recibido]"
                    else:
                        text_body = f"[Mensaje de tipo: {msg_type}]"
                        
                    if phone_number and text_body:
                        # Procesamiento asíncrono en background
                        async def procesar_y_loguear_whatsapp(num, msg_txt):
                            try:
                                respuesta = await procesar_inteligencia_agente(msg_txt, num, "whatsapp")
                                if respuesta:
                                    # TODO: Implementar la función de envío real utilizando WHATSAPP_TOKEN y WHATSAPP_PHONE_ID
                                    safe_print(f">>> [TODO] Enviar respuesta a WhatsApp {num} usando WHATSAPP_TOKEN y WHATSAPP_PHONE_ID")
                                    safe_print(f"    Respuesta que se enviará: {respuesta}")
                            except Exception as ex:
                                safe_print(f"Error procesando en WhatsApp background: {ex}")
                                
                        background_tasks.add_task(procesar_y_loguear_whatsapp, phone_number, text_body)
                        
    except Exception as e:
        safe_print(f">>> [WHATSAPP WEBHOOK] Error general procesando webhook: {e}")
        
    return {"status": "ok"}


@app.get("/privacidad", response_class=HTMLResponse)
async def get_privacidad():
    html_content = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Política de Privacidad - Matelu Store</title><style>body{font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:800px;margin:0 auto;padding:20px;}h1,h2{color:#2b6cb0;}</style></head>
<body>
<h1>Política de Privacidad y Tratamiento de Datos</h1>
<p><strong>Responsable:</strong> Marcos Guillermo Mogollón Ortega | <strong>Comercio:</strong> Matelu Store | <strong>Contacto:</strong> matelu.store2@gmail.com</p>
<h2>1. Datos Recopilados</h2>
<p>Recolectamos números de teléfono, identificadores de usuario, historiales de chat y comprobantes de pago compartidos voluntariamente en WhatsApp y Telegram para proveer soporte técnico y ventas automatizadas mediante nuestro bot de Inteligencia Artificial.</p>
<h2>2. Finalidad y Almacenamiento</h2>
<p>Los datos son almacenados en servidores cifrados y se utilizan estrictamente para mantener el contexto de la conversación, gestionar activaciones de servicios y enviar notificaciones operativas. Los mensajes son procesados por APIs de Inteligencia artificial bajo protocolos seguros.</p>
<h2>3. Eliminación de Datos de Usuario (Habeas Data)</h2>
<p>De conformidad con la Ley 1581 de 2012, para revocar la autorización o solicitar la <strong>eliminación permanente y total</strong> de sus datos, el usuario debe enviar un correo electrónico a <strong>matelu.store2@gmail.com</strong> indicando su número de teléfono. Los registros del servidor serán purgados en un máximo de 72 horas hábiles.</p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)


@app.get("/terminos", response_class=HTMLResponse)
async def get_terminos():
    html_content = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Términos del Servicio - Matelu Store</title><style>body{font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:800px;margin:0 auto;padding:20px;}h1,h2{color:#2b6cb0;}</style></head>
<body>
<h1>Términos y Condiciones del Servicio Automatizado</h1>
<h2>1. Aceptación</h2>
<p>Al interactuar con nuestros agentes oficiales en WhatsApp y Telegram, el usuario acepta ser atendido por un sistema automatizado de Inteligencia Artificial.</p>
<h2>2. Reglas de Activación de Servicios</h2>
<p><strong>IMPORTANTE:</strong> La provisión de información sobre cuentas (ej. billeteras digitales) es de carácter informativo. <strong>Ningún servicio, acceso o producto será activado o entregado hasta que el usuario haya enviado por este canal un comprobante de pago válido</strong> y este haya sido validado administrativamente.</p>
<h2>3. Uso Adecuado</h2>
<p>Queda prohibido enviar spam, ataques informáticos o inyecciones de código al agente. El incumplimiento resultará en un bloqueo permanente del usuario.</p>
</body>
</html>"""
    return HTMLResponse(content=html_content, status_code=200)
