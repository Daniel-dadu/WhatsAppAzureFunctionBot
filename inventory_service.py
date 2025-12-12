
from typing import List, Dict, Any, Union
import re
from maquinaria_config import machinery_config_service

class InventoryService:
    """
    Servicio para buscar y filtrar maquinaria del inventario
    basado en los requerimientos del usuario.
    """
    
    def __init__(self, cosmos_client=None, database_name=None):
        self.config_service = machinery_config_service
        self.container = None
        
        if cosmos_client and database_name:
            database = cosmos_client.get_database_client(database_name)
            self.container = database.get_container_client("machinery_inventory")
            
        # Fallback for offline testing if no client provided
        self._local_inventory_fallback = []

    def find_matching_machines(self, machine_type: str, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Encuentra máquinas que coincidan con los requerimientos.
        """
        # Fetch inventory
        if self.container:
            # Opción 1: Query a la DB filtering por partition key (categoria) si es posible
            # machine_type id usually matches categoria logic
            inventory_items = self._fetch_from_db(machine_type)
        else:
            inventory_items = self._local_inventory_fallback

        # Filter in memory (logic remains same for now)
        filtered_machines = [
            m for m in inventory_items
            if self._matches_category(m, machine_type)
        ]
        
        if not filtered_machines:
            return []

        # Obtener configuración de campos para saber cómo comparar
        config = self.config_service.get_config(machine_type)
        if not config:
            return filtered_machines # Si no hay config, devolvemos todo lo de la categoría
            
        matching_machines = []
        
        for machine in filtered_machines:
            if self._check_requirements(machine, requirements, config.fields):
                matching_machines.append(machine)
                
        return matching_machines

    def _fetch_from_db(self, machine_type: str) -> List[Dict[str, Any]]:
        """
        Obtiene ítems desde Cosmos DB. 
        Intenta filtrar por categoría si es posible, o trae todo (menos eficiente pero seguro para MVP).
        """
        try:
            # Nota: 'machine_type' (ej: 'soldadora') podría usarse como partition key /categoria en algunos casos
            # Pero como inventario.py tiene categorias que no siempre hacen match 1:1, 
            # hacemos un query amplio o intentamos filtrar por el string.
            
            # Para eficiencia, intentemos filtrar por categoría aproximada si sabemos que es partition key
            # query = f"SELECT * FROM c WHERE c.categoria = '{machine_type}'"
            # Pero dado el fuzzy match de _matches_category, mejor traemos todo o hacemos un query CONTAINS.
            # Cosmos no soporta CONTAINS scan eficiente en todos los casos, pero para este volumen está bien.
            
            # Query broad:
            query = "SELECT * FROM c"
            items = list(self.container.query_items(
                query=query,
                enable_cross_partition_query=True
            ))
            return items
        except Exception as e:
            print(f"Error fetching inventory from Cosmos: {e}")
            return []

    def _matches_category(self, machine: Dict[str, Any], machine_type: str) -> bool:
        """Verifica si la máquina pertenece a la categoría solicitada"""
        # Mapeo simple de categorías conocidas para búsquedas más flexibles si es necesario
        # Ahora machine_type es un string (ej: "soldadora", "plataforma") que coincide con el ID de la config
        
        target_keyword = machine_type.lower()
        machine_cat = machine.get("categoria", "").lower()
        
        # Coincidencia directa o parcial
        return target_keyword in machine_cat or machine_cat in target_keyword

    def _check_requirements(self, machine: Dict[str, Any], requirements: Dict[str, Any], fields_config: List[Any]) -> bool:
        """Verifica si una máquina específica cumple con todos los requerimientos"""
        
        for field in fields_config:
            # Si el usuario no especificó este requerimiento, saltar
            if field.name not in requirements or not requirements[field.name]:
                continue
                
            req_value = requirements[field.name]
            machine_value = machine.get(field.name)
            
            # Si la máquina no tiene el dato, asumimos que NO cumple (o discutible)
            # Para este MVP, si falta el dato en inventario, no lo recomendamos.
            if machine_value is None:
                continue 

            if not self._compare_values(req_value, machine_value, field.comparison_operator, field.type):
                return False
                
        return True

    def _compare_values(self, req_val: Any, mach_val: Any, operator: str, data_type: str) -> bool:
        """
        Compara valores usando el operador especificado.
        Intenta convertir a números si es necesario.
        """
        try:
            # Normalización básica
            req_val_norm = self._normalize_value(req_val, data_type)
            mach_val_norm = self._normalize_value(mach_val, data_type)
            
            if req_val_norm is None or mach_val_norm is None:
                return False

            if operator == "gte": # Mayor o igual (para capacidades, alturas)
                return float(mach_val_norm) >= float(req_val_norm)
            
            elif operator == "lte": # Menor o igual
                return float(mach_val_norm) <= float(req_val_norm)
            
            elif operator == "eq": # Igualdad estricta
                return str(mach_val_norm).lower() == str(req_val_norm).lower()
            
            elif operator == "contains": # Contenido (fuzzy match)
                return str(req_val_norm).lower() in str(mach_val_norm).lower()

            return False
            
        except Exception as e:
            # Si falla la conversión o comparación, asumimos falso
            return False

    def _normalize_value(self, value: Any, data_type: str) -> Union[float, str, bool, None]:
        """Limpia y convierte valores para comparación"""
        if value is None:
            return None
            
        str_val = str(value).strip()
        
        if data_type == "number":
            # Extraer solo el primer número encontrado (ej: "20.12 m" -> 20.12)
            match = re.search(r"[-+]?\d*\.\d+|\d+", str_val)
            if match:
                return float(match.group())
            return None
            
        if data_type == "boolean":
            return str_val.lower() in ["true", "si", "sí", "yes", "1"]
            
        return str_val
