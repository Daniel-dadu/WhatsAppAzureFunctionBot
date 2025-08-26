"""
Bot de WhatsApp para el chatbot
"""

import json
import logging
import os
import requests
from ai_langchain import AzureOpenAIConfig, IntelligentLeadQualificationChatbot

# ============================================================================
# CLASE PRINCIPAL DEL BOT DE WHATSAPP
# ============================================================================

class WhatsAppBot:
    def __init__(self):
        self.access_token = os.environ['WHATSAPP_ACCESS_TOKEN']
        self.phone_number_id = os.environ['PHONE_NUMBER_ID']
        self.version = os.environ['WHATSAPP_API_VERSION']
        
        # Inicializar la configuración de LangChain
        self.langchain_config = None
        self._initialize_langchain_config()
        
        # Diccionario para mantener el estado de las conversaciones por usuario
        self.conversations = {}
        
    def _initialize_langchain_config(self):
        """Inicializa la configuración de LangChain con Azure OpenAI"""
        try:
            self.langchain_config = AzureOpenAIConfig(
                endpoint=os.environ["FOUNDRY_ENDPOINT"],
                api_key=os.environ["FOUNDRY_API_KEY"],
                deployment_name="gpt-4.1-mini",
                api_version="2024-12-01-preview",
                model_name="gpt-4.1-mini"
            )
            logging.info("Configuración de LangChain inicializada correctamente")
        except Exception as e:
            logging.error(f"Error inicializando configuración de LangChain: {e}")
            raise
        
    def normalize_mexican_number(self, phone_number: str) -> str:
        """
        Normaliza un número mexicano en formato internacional para que sea aceptado por la API de WhatsApp.
        Si el número comienza con '521' (México + celular), elimina el '1' extra.
        """
        if phone_number.startswith("521") and len(phone_number) >= 12:
            return "52" + phone_number[3:]
        return phone_number
    
    def get_text_message_input(self, recipient: str, text: str) -> str:
        """
        Crea el payload JSON para enviar un mensaje de texto vía WhatsApp API.
        """
        normalized_recipient = self.normalize_mexican_number(recipient)
        return json.dumps({
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_recipient,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": text
            },
        })
    
    def send_message(self, wa_id: str, text: str) -> bool:
        """
        Envía un mensaje a través de WhatsApp API.
        """
        try:
            data = self.get_text_message_input(wa_id, text)
            headers = {
                "Content-type": "application/json",
                "Authorization": f"Bearer {self.access_token}",
            }
            
            url = f"https://graph.facebook.com/{self.version}/{self.phone_number_id}/messages"
            response = requests.post(url, data=data, headers=headers, timeout=10)
            response.raise_for_status()
            
            logging.info(f"Mensaje enviado exitosamente a {wa_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error enviando mensaje a {wa_id}: {e}")
            return False
    
    def process_message(self, wa_id: str, message_text: str) -> str:
        """
        Procesa un mensaje entrante y retorna la respuesta usando LangChain.
        """
        try:
            # Verificar si es un comando especial
            if message_text.lower() == "reset":
                return self._handle_reset_command(wa_id)
            elif message_text.lower() == "status":
                return self._get_conversation_status(wa_id)
            
            # Procesar mensaje con LangChain
            return self._process_message_with_langchain(wa_id, message_text)
                
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return "Disculpa, hubo un problema técnico. ¿Podrías repetir tu mensaje?"
    
    def _handle_reset_command(self, wa_id: str) -> str:
        """Maneja el comando de reset"""
        if wa_id in self.conversations:
            del self.conversations[wa_id]
            logging.info(f"Conversación reiniciada para usuario {wa_id}")
        return "Conversación reiniciada. Puedes comenzar de nuevo."
    
    def _process_message_with_langchain(self, wa_id: str, message_text: str) -> str:
        """Procesa mensaje usando la API de LangChain"""
        try:
            # Obtener o crear instancia del chatbot para este usuario
            if wa_id not in self.conversations:
                self.conversations[wa_id] = IntelligentLeadQualificationChatbot(self.langchain_config)
                logging.info(f"Nueva conversación iniciada para usuario {wa_id}")
            
            chatbot = self.conversations[wa_id]
            
            # Procesar mensaje con LangChain
            response = chatbot.send_message(message_text)
            
            # Verificar si la conversación está completa
            if chatbot.state["completed"]:
                logging.info(f"Conversación completada para usuario {wa_id}")
                # Opcional: aquí podrías sincronizar con HubSpot si es necesario
                
            return response
            
        except Exception as e:
            logging.error(f"Error procesando mensaje con LangChain: {e}")
            return "Disculpa, hubo un problema técnico. ¿Podrías repetir tu mensaje?"
    

    
    def is_authorized_user(self, wa_id: str) -> bool:
        """
        Verifica si el usuario está autorizado para usar el bot.
        """
        authorized_ids = [
            os.environ['RECIPIENT_WAID'],
            "5212212122080",
            "5219512397285"
        ]
        return wa_id in authorized_ids
    
    def get_conversation_summary(self, wa_id: str) -> dict:
        """
        Obtiene un resumen de la conversación actual del usuario.
        """
        if wa_id in self.conversations:
            return self.conversations[wa_id].get_conversation_summary()
        else:
            return {"error": "No hay conversación activa para este usuario"}
    
    def _get_conversation_status(self, wa_id: str) -> str:
        """
        Obtiene el estado actual de la conversación del usuario.
        Útil para debugging y monitoreo.
        """
        try:
            if wa_id in self.conversations:
                chatbot = self.conversations[wa_id]
                state = chatbot.state
                return f"""📊 ESTADO DE CONVERSACIÓN:
🤖 API: LangChain (IntelligentLeadQualificationChatbot)
👤 Usuario: {wa_id}
✅ Completada: {'Sí' if state.get('completed', False) else 'No'}
📝 Nombre: {state.get('nombre', 'No especificado')}
🔧 Tipo maquinaria: {state.get('tipo_maquinaria', 'No especificado')}
🌐 Sitio web: {state.get('sitio_web', 'No especificado')}
💼 Uso: {state.get('uso_empresa_o_venta', 'No especificado')}
📧 Correo: {state.get('correo', 'No especificado')}
📱 Teléfono: {state.get('telefono', 'No especificado')}
💬 Total mensajes: {len(state.get('messages', []))}"""
            else:
                return f"📊 No hay conversación activa para el usuario {wa_id}"
        except Exception as e:
            logging.error(f"Error obteniendo estado de conversación: {e}")
            return f"❌ Error obteniendo estado: {str(e)}"
    
# ============================================================================
# COMANDOS DISPONIBLES PARA EL USUARIO
# ============================================================================
# 
# Comandos especiales que puedes enviar por WhatsApp:
# 
# 🔄 "reset" - Reinicia la conversación actual
# 📊 "status" - Muestra el estado actual de la conversación
# 
# ============================================================================
