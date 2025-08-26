"""
Modelos de datos para el chatbot
"""

from dataclasses import dataclass
from typing import Optional, List

@dataclass
class Lead:
    wa_id: str
    name: Optional[str] = None
    equipment_interest: Optional[str] = None
    machine_characteristics: Optional[List[str]] = None
    current_question_index: Optional[int] = None
    is_distributor: Optional[bool] = None
    company_name: Optional[str] = None
    company_business: Optional[str] = None
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