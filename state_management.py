from abc import ABC, abstractmethod
from typing import Optional, TypedDict, List, Dict, Any
from enum import Enum

class MaquinariaType(str, Enum):
    SOLDADORAS = "soldadoras"
    COMPRESOR = "compresor"
    TORRE_ILUMINACION = "torre_iluminacion"
    LGMG = "lgmg"
    GENERADORES = "generadores"
    ROMPEDORES = "rompedores"

class ConversationState(TypedDict):
    messages: List[Dict[str, str]]
    nombre: Optional[str]
    tipo_maquinaria: Optional[MaquinariaType]
    detalles_maquinaria: Dict[str, Any]
    sitio_web: Optional[str]
    uso_empresa_o_venta: Optional[str]
    nombre_completo: Optional[str]
    nombre_empresa: Optional[str]
    giro_empresa: Optional[str]
    correo: Optional[str]
    telefono: Optional[str]
    completed: bool

class ConversationStateStore(ABC):
    """Interfaz para almacenar y recuperar estados de conversación"""
    
    @abstractmethod
    def get_conversation_state(self, user_id: str) -> Optional[ConversationState]:
        """Recupera el estado de conversación para un usuario"""
        pass
    
    @abstractmethod
    def save_conversation_state(self, user_id: str, state: ConversationState) -> None:
        """Guarda el estado de conversación para un usuario"""
        pass
    
    @abstractmethod
    def delete_conversation_state(self, user_id: str) -> None:
        """Elimina el estado de conversación para un usuario"""
        pass

class InMemoryStateStore(ConversationStateStore):
    """Implementación en memoria para testing"""
    
    def __init__(self):
        self._states = {}
    
    def get_conversation_state(self, user_id: str) -> Optional[ConversationState]:
        return self._states.get(user_id)
    
    def save_conversation_state(self, user_id: str, state: ConversationState) -> None:
        self._states[user_id] = state.copy()  # Hacer copia para evitar referencias
    
    def delete_conversation_state(self, user_id: str) -> None:
        self._states.pop(user_id, None)

class CosmosDBStateStore(ConversationStateStore):
    """Implementación con Cosmos DB para producción"""
    
    def __init__(self, cosmos_client, database_name: str, container_name: str):
        self.cosmos_client = cosmos_client
        self.database_name = database_name
        self.container_name = container_name
    
    def get_conversation_state(self, user_id: str) -> Optional[ConversationState]:
        # Tu implementación de Cosmos DB aquí
        pass
    
    def save_conversation_state(self, user_id: str, state: ConversationState) -> None:
        # Tu implementación de Cosmos DB aquí
        pass
    
    def delete_conversation_state(self, user_id: str) -> None:
        # Tu implementación de Cosmos DB aquí
        pass