"""
Bot de WhatsApp para el chatbot
"""

import json
import logging
import os
import requests
from conversation import ConversationManager
from ai_langchain import AzureOpenAIConfig, IntelligentLeadQualificationChatbot

# ============================================================================
# CONFIGURACIÓN GLOBAL PARA CAMBIAR ENTRE APIS DE CONVERSACIÓN
# ============================================================================

# Variable global para controlar qué API de conversación usar
# True = Usar LangChain (IntelligentLeadQualificationChatbot)
# False = Usar sistema original (ConversationManager)
# 
# INSTRUCCIONES PARA CAMBIAR ENTRE APIS:
# 1. Cambiar esta variable a True para usar LangChain
# 2. Cambiar esta variable a False para usar el sistema original
# 3. También se puede cambiar dinámicamente enviando el comando "switch_langchain" o "switch_original"
# 4. El sistema detectará automáticamente errores y cambiará a la API original si es necesario
USE_LANGCHAIN_CONVERSATION = True

# ============================================================================
# CLASE PRINCIPAL DEL BOT DE WHATSAPP
# ============================================================================

class WhatsAppBot:
    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager
        self.access_token = os.environ['WHATSAPP_ACCESS_TOKEN']
        self.phone_number_id = os.environ['PHONE_NUMBER_ID']
        self.version = os.environ['WHATSAPP_API_VERSION']
        
        # Inicializar el chatbot de LangChain si se va a usar
        self.langchain_chatbot = None
        if USE_LANGCHAIN_CONVERSATION:
            self._initialize_langchain_chatbot()
        
        # Diccionario para mantener el estado de las conversaciones por usuario
        # Solo se usa cuando USE_LANGCHAIN_CONVERSATION = True
        self.langchain_conversations = {}
        
    def _initialize_langchain_chatbot(self):
        """Inicializa el chatbot de LangChain con la configuración de Azure OpenAI"""
        try:
            azure_config = AzureOpenAIConfig(
                endpoint=os.environ["FOUNDRY_ENDPOINT"],
                api_key=os.environ["FOUNDRY_API_KEY"],
                deployment_name="gpt-4.1-mini",
                api_version="2024-12-01-preview",
                model_name="gpt-4.1-mini"
            )
            self.langchain_chatbot = azure_config
            logging.info("Chatbot de LangChain inicializado correctamente")
        except Exception as e:
            logging.error(f"Error inicializando chatbot de LangChain: {e}")
            # Si falla la inicialización, cambiar a la API original
            global USE_LANGCHAIN_CONVERSATION
            USE_LANGCHAIN_CONVERSATION = False
            logging.warning("Cambiando a API de conversación original debido a error en LangChain")
        
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
        Procesa un mensaje entrante y retorna la respuesta.
        Usa la API de conversación configurada globalmente.
        """
        try:
            # Verificar si es un comando especial
            if message_text.lower() == "reset":
                return self._handle_reset_command(wa_id)
            elif message_text.lower() == "switch_langchain":
                return self.switch_conversation_api(True)
            elif message_text.lower() == "switch_original":
                return self.switch_conversation_api(False)
            elif message_text.lower() == "status":
                return self._get_conversation_status(wa_id)
            
            # Procesar mensaje según la API configurada
            if USE_LANGCHAIN_CONVERSATION:
                return self._process_message_with_langchain(wa_id, message_text)
            else:
                return self._process_message_with_original_api(wa_id, message_text)
                
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
            return "Disculpa, hubo un problema técnico. ¿Podrías repetir tu mensaje?"
    
    def _handle_reset_command(self, wa_id: str) -> str:
        """Maneja el comando de reset para ambas APIs"""
        if USE_LANGCHAIN_CONVERSATION:
            # Reset para LangChain
            if wa_id in self.langchain_conversations:
                del self.langchain_conversations[wa_id]
                logging.info(f"Conversación de LangChain reiniciada para usuario {wa_id}")
            return "Conversación reiniciada. Puedes comenzar de nuevo."
        else:
            # Reset para API original
            self.conversation_manager.reset_conversation_with_new_contact(wa_id)
            return "Conversación reiniciada. Se ha creado un nuevo contacto en el CRM. Puedes comenzar de nuevo."
    
    def _process_message_with_langchain(self, wa_id: str, message_text: str) -> str:
        """Procesa mensaje usando la API de LangChain"""
        try:
            # Obtener o crear instancia del chatbot para este usuario
            if wa_id not in self.langchain_conversations:
                self.langchain_conversations[wa_id] = IntelligentLeadQualificationChatbot(self.langchain_chatbot)
                logging.info(f"Nueva conversación de LangChain iniciada para usuario {wa_id}")
            
            chatbot = self.langchain_conversations[wa_id]
            
            # Procesar mensaje con LangChain
            response = chatbot.send_message(message_text)
            
            # Verificar si la conversación está completa
            if chatbot.state["completed"]:
                logging.info(f"Conversación de LangChain completada para usuario {wa_id}")
                # Opcional: aquí podrías sincronizar con HubSpot si es necesario
                
            return response
            
        except Exception as e:
            logging.error(f"Error procesando mensaje con LangChain: {e}")
            # En caso de error, cambiar a la API original temporalmente
            global USE_LANGCHAIN_CONVERSATION
            USE_LANGCHAIN_CONVERSATION = False
            logging.warning("Cambiando temporalmente a API original debido a error en LangChain")
            return self._process_message_with_original_api(wa_id, message_text)
    
    def _process_message_with_original_api(self, wa_id: str, message_text: str) -> str:
        """Procesa mensaje usando la API original (ConversationManager)"""
        try:
            response = self.conversation_manager.process_message(wa_id, message_text)
            return response
        except Exception as e:
            logging.error(f"Error procesando mensaje con API original: {e}")
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
        Funciona para ambas APIs de conversación.
        """
        if USE_LANGCHAIN_CONVERSATION:
            if wa_id in self.langchain_conversations:
                return self.langchain_conversations[wa_id].get_conversation_summary()
            else:
                return {"error": "No hay conversación activa para este usuario"}
        else:
            # Para la API original, devolver información básica
            conv = self.conversation_manager.get_conversation(wa_id)
            return {
                "state": conv['state'].value if hasattr(conv['state'], 'value') else str(conv['state']),
                "lead": {
                    "wa_id": conv['lead'].wa_id,
                    "name": conv['lead'].name,
                    "equipment_interest": conv['lead'].equipment_interest
                },
                "messages_total": len(conv['history'])
            }
    
    def _get_conversation_status(self, wa_id: str) -> str:
        """
        Obtiene el estado actual de la conversación del usuario.
        Útil para debugging y monitoreo.
        """
        try:
            if USE_LANGCHAIN_CONVERSATION:
                if wa_id in self.langchain_conversations:
                    chatbot = self.langchain_conversations[wa_id]
                    state = chatbot.state
                    return f"""📊 ESTADO DE CONVERSACIÓN (LangChain):
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
                    return f"📊 No hay conversación activa para el usuario {wa_id} (LangChain)"
            else:
                conv = self.conversation_manager.get_conversation(wa_id)
                return f"""📊 ESTADO DE CONVERSACIÓN (Original):
🤖 API: Sistema Original (ConversationManager)
👤 Usuario: {wa_id}
📝 Estado: {conv['state'].value if hasattr(conv['state'], 'value') else str(conv['state'])}
👤 Nombre: {conv['lead'].name or 'No especificado'}
🔧 Equipo interés: {conv['lead'].equipment_interest or 'No especificado'}
💬 Total mensajes: {len(conv['history'])}"""
        except Exception as e:
            logging.error(f"Error obteniendo estado de conversación: {e}")
            return f"❌ Error obteniendo estado: {str(e)}"
    
    def switch_conversation_api(self, use_langchain: bool) -> str:
        """
        Cambia dinámicamente entre las dos APIs de conversación.
        Útil para testing y debugging.
        """
        global USE_LANGCHAIN_CONVERSATION
        
        if use_langchain and not self.langchain_chatbot:
            # Intentar inicializar LangChain si no está disponible
            self._initialize_langchain_chatbot()
            if not self.langchain_chatbot:
                return "Error: No se pudo inicializar LangChain. Manteniendo API original."
        
        USE_LANGCHAIN_CONVERSATION = use_langchain
        
        if use_langchain:
            return "🔄 API de conversación cambiada a LangChain (IntelligentLeadQualificationChatbot)"
        else:
            return "🔄 API de conversación cambiada a sistema original (ConversationManager)"

# ============================================================================
# COMANDOS DISPONIBLES PARA EL USUARIO
# ============================================================================
# 
# Comandos especiales que puedes enviar por WhatsApp:
# 
# 🔄 "reset" - Reinicia la conversación actual
# 🔄 "switch_langchain" - Cambia a la API de LangChain
# 🔄 "switch_original" - Cambia a la API original
# 📊 "status" - Muestra el estado actual de la conversación
# 
# ============================================================================
