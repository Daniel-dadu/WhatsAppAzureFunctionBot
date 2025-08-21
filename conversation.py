"""
Gestión de conversaciones del chatbot
"""

from datetime import datetime
from typing import Dict
from models import Lead, ConversationState
from inventory import InventoryManager
from hubspot import HubSpotManager
from llm import LLMManager
import logging

class ConversationManager:
    def __init__(self, inventory_manager: InventoryManager, 
                 hubspot_manager: HubSpotManager,
                 llm_manager: LLMManager):
        self.inventory = inventory_manager
        self.hubspot = hubspot_manager
        self.llm = llm_manager
        self.conversations: Dict[str, Dict] = {}
    
    def get_conversation(self, wa_id: str) -> Dict:
        """Obtiene o crea una conversación"""
        if wa_id not in self.conversations:
            self.conversations[wa_id] = {
                'state': ConversationState.INITIAL,
                'lead': Lead(wa_id=wa_id, created_at=datetime.now().isoformat()),
                'history': [],
                'inventory_results': []
            }
        return self.conversations[wa_id]
    
    def process_message(self, wa_id: str, message: str) -> str:
        """Procesa un mensaje y genera respuesta"""
        conv = self.get_conversation(wa_id)
        current_state = conv['state']
        lead = conv['lead']

        # Agregar mensaje del usuario al historial
        conv['history'].append({"role": "user", "content": message})
        
        # Procesar según el estado actual
        logging.info(f"Procesando mensaje en estado: {current_state.value}")
        
        if current_state == ConversationState.INITIAL:
            # En el estado inicial, solo cambiar a WAITING_NAME después de generar la respuesta
            pass

        elif current_state == ConversationState.WAITING_NAME:
            lead.name = self.llm.extract_field(message, "name")
            logging.info(f"Nombre extraído: {lead.name}")
            if lead.name:
                conv['state'] = ConversationState.WAITING_EQUIPMENT
                self._sync_to_hubspot(lead)

        elif current_state == ConversationState.WAITING_EQUIPMENT:
            lead.equipment_interest = self.llm.extract_field(message, "equipment")
            logging.info(f"Equipo de interés extraído: {lead.equipment_interest}")
            if lead.equipment_interest:
                # Inicializar lista de características de máquina y índice de pregunta
                lead.machine_characteristics = []
                lead.current_question_index = 0
                conv['state'] = ConversationState.WAITING_EQUIPMENT_QUESTIONS
                self._sync_to_hubspot(lead)

        elif current_state == ConversationState.WAITING_EQUIPMENT_QUESTIONS:
            # Agregar la respuesta a las características de la máquina
            if lead.machine_characteristics is None:
                lead.machine_characteristics = []
            
            # Crear una descripción de la respuesta basada en el tipo de equipo y pregunta actual
            equipment_type = lead.equipment_interest.lower()
            characteristic_description = self._create_characteristic_description(equipment_type, message, lead.current_question_index)
            
            if characteristic_description:
                lead.machine_characteristics.append(characteristic_description)
                logging.info(f"Característica agregada: {characteristic_description}")
            
            # Verificar si hay más preguntas que hacer
            if self._has_more_questions(equipment_type, lead.current_question_index):
                # Incrementar índice de pregunta y continuar en el mismo estado
                lead.current_question_index += 1
                logging.info(f"Siguiente pregunta para {equipment_type}, índice: {lead.current_question_index}")
                self._sync_to_hubspot(lead)
            else:
                # No hay más preguntas, cambiar al siguiente estado (cotización)
                conv['state'] = ConversationState.WAITING_QUOTATION_DATA
                logging.info(f"Todas las preguntas completadas para {equipment_type}, cambiando a WAITING_QUOTATION_DATA")
                self._sync_to_hubspot(lead)

        elif current_state == ConversationState.WAITING_QUOTATION_DATA:
            # Extraer todos los datos de cotización de una vez
            quotation_data = self.llm.extract_quotation_data(message)
            logging.info(f"Datos de cotización extraídos: {quotation_data}")
            
            if quotation_data:
                # Actualizar el lead con los datos extraídos
                if quotation_data.get('name'):
                    lead.name = quotation_data['name']
                if quotation_data.get('company_name'):
                    lead.company_name = quotation_data['company_name']
                if quotation_data.get('company_business'):
                    lead.company_business = quotation_data['company_business']
                if quotation_data.get('email'):
                    lead.email = quotation_data['email']
                if quotation_data.get('phone'):
                    lead.phone = quotation_data['phone']
                
                # Marcar como completado
                conv['state'] = ConversationState.COMPLETED
                self._sync_to_hubspot(lead)

        # Si la conversación está completada, enviar mensaje de despedida
        if conv['state'] == ConversationState.COMPLETED:
            response = f"Perfecto {lead.name}, un asesor se pondrá en contacto contigo pronto para dar seguimiento a tu solicitud de {lead.equipment_interest}. ¡Gracias por tu interés!"
            
            # TODO: Guardar conversación completada
        else:
            # Generar respuesta con LLM para otros estados
            response = self.llm.generate_response(
                conv['history'], 
                conv['state'], 
                conv.get('inventory_results'),
                {
                    'equipment_interest': lead.equipment_interest,
                    'current_question_index': lead.current_question_index
                }
            )

        # Agregar respuesta al historial
        conv['history'].append({"role": "assistant", "content": response})

        # Cambiar estado después de generar respuesta en estado inicial
        if current_state == ConversationState.INITIAL:
            conv['state'] = ConversationState.WAITING_NAME
            logging.info(f"Estado cambiado de INITIAL a WAITING_NAME")

        # Limpiar historial si es muy largo
        if len(conv['history']) > 20:
            conv['history'] = conv['history'][-10:]

        return response
    
    def _create_characteristic_description(self, equipment_type: str, message: str, question_index: int) -> str:
        """Crea una descripción de la característica basada en el tipo de equipo y el índice de pregunta"""
        equipment_type = equipment_type.lower()
        
        if 'soldadora' in equipment_type or 'soldar' in equipment_type:
            return f"Amperaje/electrodo requerido: {message}"
        elif 'compresor' in equipment_type:
            return f"Capacidad de volumen de aire/herramienta: {message}"
        elif 'torre' in equipment_type and 'iluminacion' in equipment_type:
            return f"Requerimiento LED: {message}"
        elif 'lgmg' in equipment_type:
            if question_index == 0:
                return f"Altura de trabajo necesaria: {message}"
            elif question_index == 1:
                return f"Actividad a realizar: {message}"
            elif question_index == 2:
                return f"Ubicación (exterior/interior): {message}"
            else:
                return f"Características de trabajo LGMG: {message}"
        elif 'generador' in equipment_type:
            if question_index == 0:
                return f"Actividad para la que se requiere: {message}"
            elif question_index == 1:
                return f"Capacidad en kVA o kW: {message}"
            else:
                return f"Características del generador: {message}"
        elif 'rompedor' in equipment_type:
            return f"Uso del rompedor: {message}"
        else:
            return f"Características del equipo: {message}"
    
    def _has_more_questions(self, equipment_type: str, current_question_index: int) -> bool:
        """Determina si hay más preguntas para hacer para un tipo de equipo específico."""
        equipment_type = equipment_type.lower()
        
        if 'soldadora' in equipment_type or 'soldar' in equipment_type:
            return current_question_index < 0  # Solo 1 pregunta (índice 0)
        elif 'compresor' in equipment_type:
            return current_question_index < 0  # Solo 1 pregunta (índice 0)
        elif 'torre' in equipment_type and 'iluminacion' in equipment_type:
            return current_question_index < 0  # Solo 1 pregunta (índice 0)
        elif 'lgmg' in equipment_type:
            return current_question_index < 2  # 3 preguntas (índices 0, 1, 2)
        elif 'generador' in equipment_type:
            return current_question_index < 1  # 2 preguntas (índices 0, 1)
        elif 'rompedor' in equipment_type:
            return current_question_index < 0  # Solo 1 pregunta (índice 0)
        else:
            return False
    
    def _sync_to_hubspot(self, lead: Lead):
        """Sincroniza el lead con HubSpot"""
        try:
            lead.updated_at = datetime.now().isoformat()
            contact_id = self.hubspot.create_or_update_contact(lead)
            if contact_id:
                lead.hubspot_contact_id = contact_id
                logging.info(f"Lead sincronizado exitosamente con HubSpot. Contact ID: {contact_id}")
            else:
                logging.warning(f"No se pudo sincronizar el lead con HubSpot para WhatsApp ID: {lead.wa_id}")
        except Exception as e:
            logging.error(f"Error sincronizando con HubSpot: {e}")
    
    def reset_conversation_with_new_contact(self, wa_id: str):
        """Reinicia una conversación y crea un nuevo contacto en HubSpot"""
        if wa_id in self.conversations:
            # Reiniciar conversación
            del self.conversations[wa_id]
            logging.info(f"Conversación reiniciada para usuario {wa_id}")
        
        # Crear nueva conversación con nuevo lead
        new_lead = Lead(wa_id=wa_id, created_at=datetime.now().isoformat())
        
        # Crear nuevo contacto en HubSpot
        try:
            contact_id = self.hubspot.create_new_contact(new_lead)
            if contact_id:
                new_lead.hubspot_contact_id = contact_id
                logging.info(f"Nuevo contacto creado en HubSpot para reset. Contact ID: {contact_id}")
            else:
                logging.warning(f"No se pudo crear nuevo contacto en HubSpot para reset. WhatsApp ID: {wa_id}")
        except Exception as e:
            logging.error(f"Error creando nuevo contacto en HubSpot para reset: {e}")
        
        # Inicializar nueva conversación
        self.conversations[wa_id] = {
            'state': ConversationState.INITIAL,
            'lead': new_lead,
            'history': [],
            'inventory_results': []
        }
        logging.info(f"Nueva conversación inicializada para usuario {wa_id} con nuevo contacto en HubSpot")