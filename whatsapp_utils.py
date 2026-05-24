import os
import httpx
import base64
import io

async def descargar_imagen_whatsapp(image_id: str) -> str:
    """
    Descarga una imagen desde los servidores de Meta WhatsApp Cloud API
    utilizando el ID del archivo y la retorna en formato Base64.
    
    Soporta identificadores especiales de Mocks para simulación local.
    """
    # Soporte para Mocks en testing local
    if image_id in ("mock_comprobante_valido", "mock_comprobante_invalido"):
        # Imagen de 1x1 píxeles blanca para evitar llamar a la red en simulación
        return "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        
    whatsapp_token = os.environ.get("WHATSAPP_TOKEN", "")
    if not whatsapp_token:
        raise ValueError("WHATSAPP_TOKEN no está configurado en las variables de entorno.")
        
    async with httpx.AsyncClient() as client:
        # 1. Solicitar los metadatos del medio
        url_res = await client.get(
            f"https://graph.facebook.com/v18.0/{image_id}",
            headers={"Authorization": f"Bearer {whatsapp_token}"}
        )
        url_res.raise_for_status()
        url_data = url_res.json()
        download_url = url_data.get("url")
        
        if not download_url:
            raise ValueError(f"No se encontró la URL de descarga para el media_id: {image_id}")
            
        # 2. Descargar el archivo binario
        image_res = await client.get(
            download_url,
            headers={"Authorization": f"Bearer {whatsapp_token}"}
        )
        image_res.raise_for_status()
        image_bytes = io.BytesIO(image_res.content).getvalue()
    
    return base64.b64encode(image_bytes).decode('utf-8')


async def enviar_mensaje_whatsapp(to_phone: str, text: str, phone_number_id: str = None) -> bool:
    """
    Envía un mensaje de texto al cliente vía WhatsApp Cloud API.
    Implementa reintento exponencial en caso de fallo.
    """
    import asyncio
    whatsapp_phone_id = phone_number_id or os.environ.get("WHATSAPP_PHONE_ID", "")
    whatsapp_token = os.environ.get("WHATSAPP_TOKEN", "")
    
    if not whatsapp_phone_id or not whatsapp_token:
        print(">>> [WHATSAPP UTILS] WHATSAPP_PHONE_ID o WHATSAPP_TOKEN no configurados en las variables de entorno.")
        return False
        
    print(f">>> [WHATSAPP UTILS] Enviando mensaje a {to_phone} usando phone_number_id: '{whatsapp_phone_id}'")
    url = f"https://graph.facebook.com/v18.0/{whatsapp_phone_id}/messages"
    headers = {
        "Authorization": f"Bearer {whatsapp_token}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to_phone,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text
        }
    }
    
    max_retries = 3
    delay = 1.0  # Retardo inicial en segundos
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload, headers=headers, timeout=10.0)
                if response.status_code in (200, 201):
                    return True
                else:
                    print(f">>> [WHATSAPP UTILS] Intento {attempt + 1} falló con status {response.status_code}: {response.text}")
        except Exception as e:
            print(f">>> [WHATSAPP UTILS] Excepción en intento {attempt + 1}: {e}")
            
        if attempt < max_retries - 1:
            await asyncio.sleep(delay)
            delay *= 2  # Reintento exponencial
            
    return False

