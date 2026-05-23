import asyncio
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

load_dotenv()
# Importamos tu función de compilación
from agent_graph import get_compiled_graph 
from database import init_db

async def main():
    # Usamos un número dinámico para no cargar el historial previo de la base de datos
    import uuid
    thread_id = f"+521{uuid.uuid4().hex[:10]}"
    config = {"configurable": {"thread_id": thread_id}}

    print("=========================================================")
    print("🚀 SIMULADOR LOCAL: Agente de Ventas 'Google AI Pro 5 TB'")
    print("=========================================================")

    # AQUÍ ESTÁ LA MAGIA: El gestor de contexto asíncrono.
    # Mantiene la conexión a SQLite abierta durante toda la simulación de forma segura.
    import aiosqlite
    async with aiosqlite.connect("ventas.db", isolation_level=None) as conn:
        async with conn.cursor() as cursor:
            await cursor.execute("PRAGMA journal_mode=WAL")
            await cursor.execute("PRAGMA synchronous=NORMAL")
            await cursor.execute("PRAGMA busy_timeout=60000")
            await cursor.execute("PRAGMA temp_store=MEMORY")
            
        await init_db()
        memory = AsyncSqliteSaver(conn)
        await memory.setup()
        
        # 1. Compilamos el grafo inyectándole la memoria activa
        app_graph = get_compiled_graph(memory)
        
        print("\nComandos especiales disponibles:")
        print("  /comprobante_valido   - Simular envío de comprobante legible y correcto")
        print("  /comprobante_invalido - Simular envío de imagen borrosa o no válida")
        print("  salir                 - Salir del simulador")
        
        # 2. Todo el bucle de interacción se ejecuta dentro del contexto
        while True:
            user_input = input("\nCliente: ")
            if user_input.lower() in ['salir', 'exit', 'quit']:
                break
                
            state_update = {"phone_number": thread_id}
            msg_type = "text"

            if user_input.strip() == '/comprobante_valido' or user_input.strip() == '/comprobante':
                print("\n[Sistema] Simulando payload de WhatsApp con comprobante VÁLIDO...")
                msg_type = "image"
                state_update["image_media_id"] = "mock_comprobante_valido"
                message = HumanMessage(content="[Envié un comprobante de pago]")
            elif user_input.strip() == '/comprobante_invalido':
                print("\n[Sistema] Simulando payload de WhatsApp con comprobante INVÁLIDO...")
                msg_type = "image"
                state_update["image_media_id"] = "mock_comprobante_invalido"
                message = HumanMessage(content="[Envié un comprobante de pago]")
            else:
                message = HumanMessage(content=user_input)

            state_update["messages"] = [message]

            print("[Sistema] Procesando (Gemini pensando)...\n")
            
            async for event in app_graph.astream(state_update, config, stream_mode="values"):
                messages = event.get("messages", [])
                if messages:
                    last_msg = messages[-1]
                    if last_msg.type == "ai":
                        print(f"Agente (Google AI Pro): {last_msg.content}")

            # Usamos aget_state ya que la memoria es puramente asíncrona
            state = await app_graph.aget_state(config)
            
            if state.next:
                print("\n" + "="*50)
                print("🚨 [HITL DISPARADO] EL FLUJO HA SIDO PAUSADO 🚨")
                print("=========================================================")
                print(f"Siguiente nodo pendiente: {state.next}")
                print(f"Estado 'pending_human_validation': {state.values.get('pending_human_validation')}")
                print("El bot ha dejado de responder autónomamente. Esperando aprobación humana en la BD...")
                break

if __name__ == "__main__":
    asyncio.run(main())
