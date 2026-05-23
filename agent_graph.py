import os
import io
import base64
import httpx
import json
from datetime import datetime
from typing import TypedDict, Annotated, Sequence, Optional
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()
from operator import add

from langchain_core.messages import BaseMessage, SystemMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langchain_google_genai import ChatGoogleGenerativeAI

# Esquema estructurado para la extracción de metadatos de comprobantes con Vision
class MetadatosComprobante(BaseModel):
    es_comprobante_valido: bool = Field(
        description="True si la imagen es claramente un comprobante de transferencia bancaria, False si es otra cosa, está muy borrosa o cortada."
    )
    motivo_invalidez: str = Field(
        description="Si no es válido, explica brevemente por qué en tono amable. Vacío si es válido."
    )
    monto: Optional[str] = Field(
        description="El valor exacto transferido, incluyendo moneda. Ej: 50.000 COP"
    )
    fecha: Optional[str] = Field(
        description="La fecha y hora visible en el recibo."
    )
    referencia: Optional[str] = Field(
        description="El número de comprobante, ID de transacción o número de aprobación."
    )
    banco_origen: Optional[str] = Field(
        description="Nombre de la entidad (Nequi, Daviplata, Bancolombia, etc.)"
    )

# 1. Definición del Estado de LangGraph
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add]
    phone_number: str
    pending_human_validation: bool
    audio_media_id: Optional[str]
    image_media_id: Optional[str]

# 2. Configuración del LLM Multimodal
llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
)

SYSTEM_PROMPT_TEMPLATE = """<instruction_set>
  <role>
  Eres el vendedor estrella y asesor tecnológico experto para "Matelu Store". Tu objetivo principal es PERSUADIR, asesorar y CERRAR VENTAS de forma cálida, profesional y concisa, operando a través de WhatsApp y Telegram. Nunca suenes como un bot genérico; tu tono es el de un experto humano, seguro de sí mismo, cálido y resolutivo.
  </role>

  <context>
  Vendes suscripciones de **Google AI Pro 5 TB** (que incluye Gemini Advanced y 5TB de almacenamiento en la nube).
  La moneda exclusiva para todas las transacciones es **PESOS**.
  
  Catálogo de planes y precios actuales (Google AI Pro 5 TB):
{catalogo_texto}

  Base de Conocimiento - Ecosistema Google IA (Comparativa Plan Gratuito vs. Pro 5TB):
  - **Almacenamiento**: Gratuito (15 GB) vs. Pro (5 TB compartible con 5 personas). Beneficio: El Pro es un "almacén digital familiar masivo", imposible de llenar.
  - **Modelos**: Gratuito (Gemini 3.5 Flash) vs. Pro (Gemini 3.1 Pro / Omni / 3.5 Flash).
  - **Ventana de Contexto (Memoria)**: Gratuito (32K tokens = un artículo) vs. Pro (1M tokens = puede leer, comprender y recordar un libro de 700 páginas o códigos enteros sin olvidar nada).
  - **Integración Workspace**: Gratuito (No incluido, es un chat externo) vs. Pro (IA integrada en Gmail, Docs, Sheets, Vids, trabajando como un colega. Incluye Daily Brief para organizar correos y calendario automáticamente).
  - **Creación Multimedia**: Gratuito (Básico) vs. Pro (Estudio profesional con Veo para video, Flow, Nano Banana Pro para imágenes fotorrealistas y edición avanzada).
  - **Análisis/Desarrollo**: Pro incluye Antigravity CLI, Jules, Code Assist y NotebookLM avanzado (hasta 300 fuentes).
  - RESTRICCIÓN DE VERSIÓN: El ecosistema actual es estrictamente la Generación 3 (Gemini 3.5 Flash y Gemini 3.1 Pro / Omni). TIENES ESTRICTAMENTE PROHIBIDO mencionar o confirmar la existencia de Gemini 1.0 o Gemini 1.5. Si el cliente pregunta por el 1.5, corrígelo amablemente indicando que Matelu Store ofrece la nueva arquitectura 3.x.
  </context>

  <principles_persuasion>
  Debes integrar fluidamente estos gatillos mentales en tus interacciones:
  - **Vende Beneficios:** No des solo listas técnicas. Explica cómo el plan Pro ahorra tiempo, mejora el trabajo o potencia la creatividad usando la "Guía Sencilla" de la base de conocimiento.
  - **Validación y Empatía Activa:** Antes de rebatir una objeción, valídala. Si el cliente menciona el precio, responde empáticamente. Usa el nombre del cliente frecuentemente si lo conoces para generar proximidad y confianza.
  - **Autoridad y Marco de Control:** Mantén siempre el control de la conversación. No persigas ni te muestres desesperado por la venta. Tu postura es la de un experto que está evaluando si el producto es adecuado para el cliente, no al revés. Responde con certeza absoluta basada en tu base de conocimientos.
  - **Escasez y Urgencia Estructurada:** Cuando el cliente esté listo para tomar la decisión o pregunte por precios, introduce fricción positiva. "Actualmente nos quedan [X] unidades con este beneficio" o "Puedo mantenerte esta condición especial si procesamos esto hoy".
  - **Reciprocidad:** Ofrece pequeños fragmentos de valor gratuito antes de pedir el cierre de la venta.
  </principles_persuasion>

  <formatting_rules>
  - **Concisión Visual:** NUNCA envíes párrafos largos (máximo 2-3 líneas). Separa las ideas con saltos de línea dobles. Usa viñetas o emojis para que la lectura sea rápida.
  - **Formato Nativo:** Usa asteriscos para resaltar palabras clave o beneficios principales (ej. **acceso inmediato**, **Google AI Pro 5 TB**, **ahorro especial**).
  - **Emojis Estratégicos:** Úsalos para romper la monotonía visual, pero limítate a 1 o 2 por mensaje. Evita saturar. (ej. ✅, 🚀, 💡, 👇).
  - **Cierre de Venta (CTA):** NUNCA dejes un mensaje abierto. Termina SIEMPRE con una pregunta suave que empuje a la acción (ej. "¿Te gustaría activar este poder hoy mismo?", "¿Te envío los datos de pago para separar tu cupo?").
  </formatting_rules>

  <constraints>
    <rule>NUNCA uses herramientas de búsqueda web.</rule>
    <rule>Usa EXCLUSIVAMENTE los precios listados en el catálogo de arriba.</rule>
    <rule>MONEDA INMUTABLE: PESOS. Sin conversiones ni descuentos inventados.</rule>
    <rule>Restricción de catálogo: El catálogo solo contempla planes de "Google AI Pro 5 TB" con duraciones estrictas entre 1 y 18 meses.</rule>
    <rule>Restricción Absoluta (Anti-Alucinación): Bajo ninguna circunstancia debes inventar precios, políticas de devolución, características de productos o tiempos de entrega. Toda afirmación fáctica debe provenir del catálogo y la base de conocimiento de arriba.</rule>
    <rule>Honestidad Táctica: Si el cliente hace una pregunta técnica que no puedes resolver con los datos provistos, responde exactamente: "Esa es una excelente pregunta técnica. Permíteme verificar el dato exacto en el sistema para no darte información errónea. Te confirmo en un momento."</rule>
    <rule>REGLA ESTRICTA DE PAGO (INMUTABLE): Cuando el cliente confirme la compra o pida los datos de pago, DEBES responder ÚNICAMENTE con esta plantilla exacta (respetando los saltos de línea y viñetas):

📌 IMPORTANTE 
⚠️ No enviar información de pago en la conversación inicial. 
⚠️ El servicio se activa únicamente con comprobante de pago.
 
💲🪙 MEDIOS DE PAGO DISPONIBLES 🪙💵

👤Titular: Marcos Mogollón

📱NEQUI: 3188344680
👤 Mar••• Mog•••••

🅱️LLAVE: @3188344680
👤 Mar••• Gui•••••• Mog••••• Ort •••

📩 Una vez realizado el pago, envía el comprobante por aquí para procesar tu pedido.</rule>
  </constraints>
</instruction_set>"""

# 3. Nodos Funcionales
from database import obtener_planes_catalogo

async def procesar_voz(state: AgentState):
    audio_id = state.get("audio_media_id")
    if not audio_id:
        return {}

    whatsapp_token = os.environ.get("WHATSAPP_TOKEN", "")
    
    async with httpx.AsyncClient() as client:
        # 1. Obtener URL del medio
        url_res = await client.get(
            f"https://graph.facebook.com/v18.0/{audio_id}",
            headers={"Authorization": f"Bearer {whatsapp_token}"}
        )
        url_data = url_res.json()
        download_url = url_data.get("url")
        
        # 2. Descargar binario
        audio_res = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {whatsapp_token}"}
        )
        audio_bytes = io.BytesIO(audio_res.content).getvalue()
        
    # 3. Pasar a Gemini
    audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
    
    prompt = "Transcribe este mensaje de voz del cliente y resume su intención principal de compra en una oración."
    message = HumanMessage(content=[
        {"type": "text", "text": prompt},
        {
            "type": "image_url",
            "image_url": {"url": f"data:audio/ogg;base64,{audio_b64}"}
        }
    ])
    
    # Invocamos al LLM para la transcripción
    transcripcion = await llm.ainvoke([message])
    
    # Inyectamos la transcripción al estado como si el usuario lo hubiera escrito
    return {"messages": [HumanMessage(content=f"[Audio Transcrito]: {transcripcion.content}")], "audio_media_id": None}


async def procesar_comprobante(state: AgentState):
    image_id = state.get("image_media_id")
    if not image_id:
        return {}

    phone_number = state.get("phone_number")
    from database import registrar_comprobante_pago, actualizar_estado_cliente
    from whatsapp_utils import descargar_imagen_whatsapp

    # Soporte de Mocks para testing local sin invocar APIs externas
    if image_id == "mock_comprobante_valido":
        resultado = MetadatosComprobante(
            es_comprobante_valido=True,
            motivo_invalidez="",
            monto="50.000 Pesos",
            fecha="2026-05-21 15:30:00",
            referencia="MOCK123456789",
            banco_origen="Bancolombia"
        )
    elif image_id == "mock_comprobante_invalido":
        resultado = MetadatosComprobante(
            es_comprobante_valido=False,
            motivo_invalidez="la imagen está muy borrosa o no parece ser un comprobante de pago bancario",
            monto=None,
            fecha=None,
            referencia=None,
            banco_origen=None
        )
    else:
        # Descarga real de WhatsApp
        try:
            base64_image = await descargar_imagen_whatsapp(image_id)
        except Exception as e:
            print(f"Error descargando la imagen de WhatsApp: {e}")
            return {
                "messages": [AIMessage(content="Disculpa, tuve un problema al descargar tu comprobante. ¿Podrías volver a enviarlo o intentar con una foto más clara? 💡")],
                "image_media_id": None,
                "pending_human_validation": False
            }

        # 3. Configurar el LLM forzando la salida estructurada
        # Usamos gemini-2.5-flash y temperature=0 para una extracción visual estructurada precisa y rápida
        llm_vision = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0)
        llm_extractor = llm_vision.with_structured_output(MetadatosComprobante)
        
        # 4. Construir el mensaje multimodal
        mensaje = HumanMessage(
            content=[
                {
                    "type": "text", 
                    "text": "Analiza esta imagen. Es un comprobante de pago bancario en pesos. Extrae los datos solicitados. Ignora saldos de cuenta, céntrate solo en el valor transferido."
                },
                {
                    "type": "image_url", 
                    "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                }
            ]
        )
        
        # 5. Ejecutar la extracción visual estructurada
        try:
            resultado = await llm_extractor.ainvoke([mensaje])
        except Exception as e:
            print(f"Error procesando visión de Gemini con Pydantic: {e}")
            return {
                "messages": [AIMessage(content="Disculpa, no logré procesar la imagen de tu comprobante. ¿Podrías enviararme una foto más nítida? 💡")],
                "image_media_id": None,
                "pending_human_validation": False
            }

    # 6. Lógica de Enrutamiento (Rechazo interactivo)
    if not resultado.es_comprobante_valido:
        # El bot no entra en silencio; pide al cliente que repita la acción de forma empática
        motivo = resultado.motivo_invalidez.strip()
        detalle_motivo = f", ya que {motivo.lower()}" if motivo else ""
        respuesta_fallo = f"Revisé la imagen, pero no logré validarla{detalle_motivo} 😅 ¿Podrías enviarme una foto más clara o la captura completa de la pantalla, por favor?"
        
        return {
            "messages": [AIMessage(content=respuesta_fallo)],
            "image_media_id": None, # Limpiamos el ID para evitar loops
            "pending_human_validation": False # Sigue activo de forma autónoma
        }

    # 7. Lógica de Éxito (Persistencia y Silencio)
    await registrar_comprobante_pago(
        customer_id=phone_number,
        media_id=image_id,
        monto=resultado.monto,
        fecha=resultado.fecha,
        referencia=resultado.referencia,
        banco=resultado.banco_origen
    )
    
    await actualizar_estado_cliente(phone_number, 'esperando_humano')

    respuesta_exito = "¡Recibí tu comprobante perfectamente! ✅ Ya envié la referencia al área de supervisión. En cuanto nos den luz verde, te libero tu acceso a Google AI Pro 5 TB por aquí mismo. ¿Te parece bien si te notifico apenas esté listo?"

    return {
        "messages": [AIMessage(content=respuesta_exito)],
        "image_media_id": None,
        "pending_human_validation": True # Se activa la interrupción HITL
    }



async def generar_respuesta_ventas(state: AgentState):
    # BYPASS DIRECTO: Si está pendiente de validación humana (ej. imagen recibida en webhook),
    # devolvemos el estado vacío para no alterar la respuesta inyectada y forzar el ruteo a interrupción.
    if state.get("pending_human_validation"):
        return {}

    messages = state.get("messages", [])
    
    # Si el último mensaje ya es una respuesta del asistente, no generamos otra
    if messages and isinstance(messages[-1], AIMessage):
        return {}

    # Obtener catálogo dinámico
    planes = await obtener_planes_catalogo()
    catalogo_texto = "\n".join([f"  - {p.duration_months} meses: {p.price} Pesos ({p.features})" for p in planes])
    
    prompt_dinamico = SYSTEM_PROMPT_TEMPLATE.replace("{catalogo_texto}", catalogo_texto)
    
    # Inyectar el system prompt si no está presente en el historial
    if not any(isinstance(m, SystemMessage) for m in messages):
        messages = [SystemMessage(content=prompt_dinamico)] + list(messages)
        
    response = await llm.ainvoke(messages)
    
    return {"messages": [response]}

async def human_validation(state: AgentState):
    # Nodo designado para HITL (Human-In-The-Loop)
    # Detiene el flujo para que un humano verifique el comprobante de pago
    return {"pending_human_validation": False}

# 4. Enrutamiento
def router_entrada(state: AgentState):
    if state.get("audio_media_id"):
        return "procesar_voz"
    elif state.get("image_media_id"):
        return "procesar_comprobante"
    return "generar_respuesta_ventas"

def router_salida(state: AgentState):
    if state.get("pending_human_validation"):
        return "human_validation"
    return END

# 5. Construcción del Grafo
workflow = StateGraph(AgentState)

workflow.add_node("procesar_voz", procesar_voz)
workflow.add_node("procesar_comprobante", procesar_comprobante)
workflow.add_node("generar_respuesta_ventas", generar_respuesta_ventas)
workflow.add_node("human_validation", human_validation)

workflow.set_conditional_entry_point(
    router_entrada,
    {
        "procesar_voz": "procesar_voz",
        "procesar_comprobante": "procesar_comprobante",
        "generar_respuesta_ventas": "generar_respuesta_ventas"
    }
)

workflow.add_edge("procesar_voz", "generar_respuesta_ventas")
workflow.add_edge("procesar_comprobante", "generar_respuesta_ventas")

workflow.add_conditional_edges(
    "generar_respuesta_ventas",
    router_salida,
    {
        "human_validation": "human_validation",
        END: END
    }
)
# Después de la revisión humana, retorna al agente de ventas
workflow.add_edge("human_validation", "generar_respuesta_ventas")

# 6. Compilación y Configuración de Checkpointer Asíncrono
def get_compiled_graph(memory):
    """
    Recibe la memoria inicializada (checkpointer) desde el orquestador principal
    y compila el grafo.
    """
    graph = workflow.compile(
        checkpointer=memory,
        interrupt_before=["human_validation"]
    )
    return graph
