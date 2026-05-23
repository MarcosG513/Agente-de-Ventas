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
