
from typing import List, Dict, Any, Union
import re
from maquinaria_config import machinery_config_service

# Importar inventario local para fallback
try:
    from update_invertory_db.inventory_data import inventario as local_inventory
except ImportError:
    local_inventory = []
    print("Warning: Could not import local inventory from update_invertory_db.inventory_data")

class InventoryService:
    """
    Servicio para buscar y filtrar maquinaria del inventario
    basado en los requerimientos del usuario.
    """
    
    def __init__(self, cosmos_client=None, database_name=None):
        self.config_service = machinery_config_service
        self.container = None
        
        if cosmos_client and database_name:
            try:
                database = cosmos_client.get_database_client(database_name)
                self.container = database.get_container_client("machinery_inventory")
            except Exception as e:
                print(f"Error initializing Cosmos DB container: {e}")
            
        # Fallback for offline testing
        self._local_inventory_fallback = local_inventory

    def find_matching_machines(self, machine_type: str, requirements: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Encuentra máquinas que coincidan con los requerimientos.
        Returns machines sorted by relevance (closest match first).
        """
        # Fetch inventory
        if self.container:
            # Opción 1: Query a la DB
            inventory_items = self._fetch_from_db(machine_type)
        else:
            inventory_items = self._local_inventory_fallback

        # Filter in memory
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
        
        # Sort by relevance: machines closest to requirements appear first
        matching_machines.sort(
            key=lambda m: self._calculate_relevance_score(m, requirements, config.fields)
        )
                
        return matching_machines

    def _fetch_from_db(self, machine_type: str) -> List[Dict[str, Any]]:
        """
        Obtiene ítems desde Cosmos DB. 
        """
        try:
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
                
            # El nombre del campo en requirements puede diferir del nombre en inventory si la extracción no es perfecta,
            # pero asumimos que la extracción usa los nombres definidos en config.fields.
            # config.fields.name apunta a la key del inventario (ej: amperaje_amps_max).
            
            req_value = requirements.get(field.name)
            # En ciertos casos, la extracción podría devolver el campo "amperaje" en lugar de "amperaje_amps_max"
            # si el nombre del campo en el prompt no fue actualizado.
            # Pero IntelligentSlotFiller usa la config para generar los prompts, 
            # así que el LLM debería extraer "amperaje_amps_max" si ese es el nombre del field.
            
            machine_value = machine.get(field.name)
            
            # Si la máquina no tiene el dato, asumimos que NO cumple 
            if machine_value is None:
                # Opcional: si es null, tal vez permitirlo? Por ahora estricto.
                continue 

            if not self._compare_values(req_value, machine_value, field.comparison_operator, field.type):
                return False
                
        return True

    def _compare_values(self, req_val: Any, mach_val: Any, operator: str, data_type: str) -> bool:
        """
        Compara valores usando el operador especificado.
        """
        try:
            # Normalización básica
            req_val_norm = self._normalize_value(req_val, data_type)
            mach_val_norm = self._normalize_value(mach_val, data_type)
            
            if req_val_norm is None or mach_val_norm is None:
                return False

            if operator == "gte": # Mayor o igual (para capacidades, alturas)
                # El valor de la máquina (capacidad) debe ser >= requerimiento
                return float(mach_val_norm) >= float(req_val_norm)
            
            elif operator == "lte": # Menor o igual
                return float(mach_val_norm) <= float(req_val_norm)
            
            elif operator == "eq": # Igualdad estricta (case insensitive)
                return str(mach_val_norm).lower() == str(req_val_norm).lower()
            
            elif operator == "contains": # Contenido (fuzzy match)
                return str(req_val_norm).lower() in str(mach_val_norm).lower()

            return False
            
        except Exception as e:
            # Si falla la conversión o comparación, asumimos falso
            return False

    def _calculate_relevance_score(self, machine: Dict[str, Any], requirements: Dict[str, Any], fields_config: List[Any]) -> float:
        """
        Calculate how closely a machine matches requirements.
        Lower score = better match (closer to exact requirements).
        """
        total_diff = 0.0
        
        for field in fields_config:
            # Only consider fields the user specified
            if field.name not in requirements or not requirements[field.name]:
                continue
            
            # Only score numeric fields with gte/lte operators
            if field.type != "number":
                continue
            
            req_val = self._normalize_value(requirements[field.name], "number")
            mach_val = self._normalize_value(machine.get(field.name), "number")
            
            if req_val is not None and mach_val is not None:
                # Absolute difference between requirement and machine spec
                total_diff += abs(float(mach_val) - float(req_val))
        
        return total_diff

    def _normalize_value(self, value: Any, data_type: str) -> Union[float, str, bool, None]:
        """Limpia y convierte valores para comparación"""
        if value is None:
            return None
            
        # Si ya es el tipo correcto, devolverlo
        if data_type == "number" and isinstance(value, (int, float)):
            return float(value)
            
        str_val = str(value).strip()
        
        if data_type == "number":
             # Intenta convertir string a float directamente
             # Si tiene texto extra (unidades), intentamos extraer el primer número
             match = re.search(r"[-+]?\d*\.\d+|\d+", str_val)
             if match:
                 return float(match.group())
             return None
            
        if data_type == "boolean":
            return str_val.lower() in ["true", "si", "sí", "yes", "1"]
            
        return str_val
