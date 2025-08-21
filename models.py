"""
Modelos de datos para el chatbot
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, List

class ConversationState(Enum):
    INITIAL = "initial"
    WAITING_NAME = "waiting_name"
    WAITING_EQUIPMENT = "waiting_equipment"
    WAITING_EQUIPMENT_QUESTIONS = "waiting_equipment_questions"
    WAITING_QUOTATION_DATA = "waiting_quotation_data"
    COMPLETED = "completed"

@dataclass
class Lead:
    wa_id: str
    name: Optional[str] = None
    equipment_interest: Optional[str] = None
    machine_characteristics: Optional[List[str]] = None  # Lista de respuestas a preguntas del equipo
    current_question_index: Optional[int] = None  # Índice de la pregunta actual en la secuencia
    is_distributor: Optional[bool] = None  # True si es distribuidor, False si es cliente final
    company_name: Optional[str] = None  # Nombre de la empresa
    company_business: Optional[str] = None  # Giro de la empresa
    email: Optional[str] = None
    phone: Optional[str] = None
    hubspot_contact_id: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

@dataclass
class InventoryItem:
    tipo_maquina: str
    modelo: str
    ubicacion: str