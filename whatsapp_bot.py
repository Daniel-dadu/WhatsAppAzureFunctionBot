"""
Bot de WhatsApp para el chatbot
"""

import json
import logging
import os
import requests
from ai_langchain import AzureOpenAIConfig, IntelligentLeadQualificationChatbot
from state_management import ConversationStateStore
from typing import Optional
from datetime import datetime, timezone
from hubspot_manager import HubSpotManager
from check_guardrails import ContentSafetyGuardrails

# ============================================================================
# CLASE PRINCIPAL DEL BOT DE WHATSAPP
# ============================================================================

class WhatsAppBot:
    def __init__(self, state_store: Optional[ConversationStateStore] = None):
        self.access_token = os.environ['WHATSAPP_ACCESS_TOKEN']
        self.phone_number_id = os.environ['PHONE_NUMBER_ID']
        self.version = os.environ['WHATSAPP_API_VERSION']
        
        # Inicializar la configuración de LangChain
        self.langchain_config = None
        self._initialize_langchain_config()
        
        # Usar el state_store proporcionado
        self.state_store = state_store

        # Una sola instancia del chatbot que manejará todos los usuarios
        self.chatbot = IntelligentLeadQualificationChatbot(self.langchain_config, self.state_store)

        # Una sola instancia del guardrails
        self.guardrails = ContentSafetyGuardrails()
        
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
            
            # logging.info(f"Mensaje enviado exitosamente a {wa_id}")
            return True
            
        except Exception as e:
            logging.error(f"Error enviando mensaje a {wa_id}: {e}")
            return False
    
    def process_message(self, wa_id: str, message_text: str, hubspot_manager: HubSpotManager) -> str:
        """
        Procesa un mensaje entrante y retorna la respuesta usando LangChain.
        """
        try:
            # Verificar si el mensaje es seguro
            safety_result = self.guardrails.check_message_safety(message_text)
            if safety_result:
                response_for_lead = "No me queda claro lo que dices. ¿Podrías explicarme mejor?"
                # Guardar mensajes de seguridad en la base de datos
                self._save_safety_messages(wa_id, safety_result["message"], message_text, response_for_lead)
                return response_for_lead

            # Verificar si es un comando especial
            if message_text.lower() == "reset":
                hubspot_manager.delete_contact()
                return self._handle_reset_command(wa_id)
            elif message_text.lower() == "status":
                return self._get_conversation_status(wa_id)
            
            # Procesar mensaje con LangChain
            response = self.chatbot.send_message(message_text, hubspot_manager)
                
            return response
            
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return "Disculpa, hubo un problema técnico. ¿Podrías repetir tu mensaje?"
    
    def _handle_reset_command(self, wa_id: str) -> str:
        """Maneja el comando de reset"""
        self.chatbot.load_conversation(wa_id)
        self.chatbot.reset_conversation()
        logging.info(f"Conversación reiniciada para usuario {wa_id}")
        return "Conversación reiniciada. Puedes comenzar de nuevo."
    
    def is_authorized_user(self, wa_id: str) -> bool:
        """
        Verifica si el usuario está autorizado para usar el bot.
        """
        authorized_ids = [
            os.environ['RECIPIENT_WAID'],
            "5212212122080",
            "5219512397285",
            "5217821730008"
        ]
        return wa_id in authorized_ids
    
    def _save_safety_messages(self, wa_id: str, safety_message: str, original_message: str, response_for_lead: str) -> None:
        """
        Guarda los mensajes de seguridad en la base de datos usando _append_messages.
        Guarda el mensaje de seguridad del bot y la respuesta genérica.
        """
        try:
            # Asegurar que el usuario tenga una conversación cargada
            self.chatbot.save_conversation()

            # Preparar los dos mensajes a guardar
            safety_messages = [
                {
                    "content": safety_message,
                    "role": "user",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # Se generará automáticamente en _append_messages
                },
                {
                    "content": response_for_lead,
                    "role": "bot",
                    "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")  # Se generará automáticamente en _append_messages
                }
            ]
            
            # Usar _append_messages para guardar los mensajes
            self.state_store._append_messages(wa_id, safety_messages)
            logging.info(f"Mensajes de seguridad guardados para usuario {wa_id}")
            
        except Exception as e:
            logging.error(f"Error guardando mensajes de seguridad para usuario {wa_id}: {e}")

    def _get_conversation_status(self, wa_id: str) -> str:
        """Obtiene el estado actual de la conversación del usuario."""
        try:
            self.chatbot.load_conversation(wa_id)
            state = self.chatbot.state
            return f"""📊 ESTADO DE CONVERSACIÓN:
        🤖 API: LangChain (IntelligentLeadQualificationChatbot)
        👤 Usuario: {wa_id}
        ✅ Completada: {'Sí' if state.get('completed', False) else 'No'}
        📝 Nombre: {state.get('nombre', 'No especificado')}
        👤 Apellido: {state.get('apellido', 'No especificado')}
        🔧 Tipo maquinaria: {state.get('tipo_maquinaria', 'No especificado')}
        🔍 Detalles maquinaria: {state.get('detalles_maquinaria', 'No especificado')}
        💼 Nombre empresa: {state.get('nombre_empresa', 'No especificado')}
        💼 Giro empresa: {state.get('giro_empresa', 'No especificado')}
        🌐 Sitio web: {state.get('sitio_web', 'No especificado')}
        💼 Tipo de uso: {state.get('uso_empresa_o_venta', 'No especificado')}
        📧 Correo: {state.get('correo', 'No especificado')}
        📱 Teléfono: {state.get('telefono', 'No especificado')}
        📍 Lugar requerimiento: {state.get('lugar_requerimiento', 'No especificado')}
        💬 Total mensajes: {len(state.get('messages', []))}
        👤 Conversación mode: {state.get('conversation_mode', 'No especificado')}
        """
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
