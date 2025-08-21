"""
Bot de WhatsApp para el chatbot
"""

import json
import logging
import os
import requests
from conversation import ConversationManager

class WhatsAppBot:
    def __init__(self, conversation_manager: ConversationManager):
        self.conversation_manager = conversation_manager
        self.access_token = os.environ['WHATSAPP_ACCESS_TOKEN']
        self.phone_number_id = os.environ['PHONE_NUMBER_ID']
        self.version = os.environ['VERSION']
        
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
        """
        try:
            # Verificar si es un comando de reset
            if message_text.lower() == "reset":
                self.conversation_manager.reset_conversation_with_new_contact(wa_id)
                return "Conversación reiniciada. Se ha creado un nuevo contacto en el CRM. Puedes comenzar de nuevo."
            
            # Procesar mensaje normal
            response = self.conversation_manager.process_message(wa_id, message_text)
            return response
            
        except Exception as e:
            logging.error(f"Error procesando mensaje: {e}")
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
