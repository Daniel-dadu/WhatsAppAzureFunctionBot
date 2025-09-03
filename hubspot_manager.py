"""
Integración con HubSpot CRM
"""

import requests
from typing import Dict, Optional
import logging
import json

# Lista de productos de interés registrados en HubSpot
PRODUCTO_INTERESADO = [
    "Soldadoras Shindaiwa",
    "Plataformas de elevación LGMG",
    "Torres de iluminación Trime",
    "Motobombas Koshin",
    "Generadores",
    "Generador portátil Koshin",
    "Martillos neumáticos Toku",
    "Cortadora de varilla Alpha C",
    "Dobladora de varilla Alpha C",
    "Compresores eléctricos Airman",
    "Compresores portátiles Airman",
    "Montacargas LGMG",
    "Manipulador LGMG",
    "Apisonador Sakai"
]

# Diccionario de productos de interés registrados en HubSpot
# TODO: mejorar clasificación de productos del bot
PRODUCTO_INTERESADO_DICT = {
    "soldadora": "Soldadoras Shindaiwa",
    "plataforma": "Plataformas de elevación LGMG",
    "torre_iluminacion": "Torres de iluminación Trime",
    "generador": "Generadores",
    "compresor": "Compresores eléctricos Airman",
    "montacargas": "Montacargas LGMG",
    "manipulador": "Manipulador LGMG",
    "apisonador": "Apisonador Sakai",
    "rompedor": "Martillos neumáticos Toku"
}

# Giro de la empresa registrado en HubSpot
GIRO_EMPRESA = [
    "Venta de maquinaria",
    "Renta de maquinaria",
    "Distribuidor",
    "Comercializadora",
    "Minería",
    "Construcción",
    "Otro"
]

# Estados registrados en HubSpot
ESTADOS = [
  "Aguascalientes",
  "Baja California",
  "Baja California Sur",
  "Campeche",
  "Chiapas",
  "Chihuahua",
  "Ciudad de México",
  "Coahuila",
  "Colima",
  "Durango",
  "Estado de México",
  "Guanajuato",
  "Guerrero",
  "Hidalgo",
  "Jalisco",
  "Michoacán",
  "Morelos",
  "Nayarit",
  "Nuevo León",
  "Oaxaca",
  "Puebla",
  "Querétaro",
  "Quintana Roo",
  "San Luis Potosí",
  "Sinaloa",
  "Sonora",
  "Tabasco",
  "Tamaulipas",
  "Tlaxcala",
  "Veracruz",
  "Yucatán",
  "Zacatecas"
]

class TokenExpired(Exception):
    pass

class HubSpotManager:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.url = "https://api.hubapi.com/crm/v3/objects/contacts"
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        self.contact_id = None

    def create_contact(self, wa_id: str, telefono: str) -> Optional[str]:
        """Crea un contacto en HubSpot"""
        try:
            # Preparar propiedades del contacto
            properties = {
                "id_conversacion_bot": "conv_" + wa_id,
                "phone": telefono,
                "lifecyclestage": "lead"
            }
            
            # Crear nuevo contacto
            logging.info("Creando nuevo contacto en HubSpot")

            # Retornar el id del contacto creado
            self.contact_id = self._create_contact(properties)
            return self.contact_id
        except Exception as e:
            logging.error(f"Error en HubSpot: {e}")
            return None
    
    def _create_contact(self, properties: Dict) -> Optional[str]:
        """Crea un nuevo contacto"""
        response = requests.post(
            f"{self.url}",
            headers=self.headers,
            json={"properties": properties}
        )
        if response.status_code == 201:
            data = response.json()
            logging.info(f"Contacto creado exitosamente: {data['id']}")
            return data['id']
        
        # Otros errores
        logging.error(f"Error creando contacto: {response.status_code}")
        logging.error(f"Respuesta de HubSpot: {response.text}")
        logging.error(f"Propiedades que se intentaron enviar: {properties}")
        return None
    
    def update_contact(self, state: Dict, extracted_info: Dict) -> Optional[str]:
        """Actualiza un contacto existente"""

        properties = {}

        try:
            logging.info(f"Actualizando contacto en HubSpot con información: {extracted_info}")

            for key, value in extracted_info.items():
                current_value = state.get(key)
                if key != "detalles_maquinaria" and current_value and current_value not in ["No especificado", "No tiene", None, ""]:
                    continue

                if key == "nombre":
                    properties["firstname"] = value

                elif key == "apellido":
                    # Combinar nombre y apellido en el campo nombre
                    nombre_actual = state.get("nombre", "")
                    if nombre_actual and value:
                        properties["firstname"] = f"{nombre_actual} {value}".strip()

                elif key == "tipo_maquinaria":
                    # TODO: mejorar con el valor real
                    properties["en_que_producto_estas_interesado_"] = PRODUCTO_INTERESADO_DICT[value]
                
                elif key == "detalles_maquinaria" and isinstance(value, dict):
                    current_detalles = state.get("detalles_maquinaria", {})
                    current_detalles.update(value)
                    # Convertir detalles_maquinaria a string
                    current_detalles_str = json.dumps(current_detalles)
                    properties["caracteristicas_de_maquinaria_de_interes"] = current_detalles_str

                elif key == "nombre_empresa":
                    properties["company"] = value

                elif key == "giro_empresa":
                    # TODO: mejorar con el valor real
                    if value in GIRO_EMPRESA:
                        properties["giro_de_la_empresa_"] = value
                    else:
                        properties["giro_de_la_empresa_"] = GIRO_EMPRESA[0]

                elif key == "lugar_requerimiento":
                    # TODO: mejorar con el valor real
                    if value in ESTADOS:
                        properties["estado___region"] = value
                    else:
                        properties["estado___region"] = ESTADOS[0]

                elif key == "telefono":
                    properties["phone"] = value

                elif key == "correo":
                    properties["email"] = value

                elif key == "sitio_web":
                    properties["pgina_web_de_tu_negocio"] = value

            return self._update_contact(properties)
        except Exception as e:
            logging.error(f"Error actualizando contacto en HubSpot: {e}")
            return None
    
    def _update_contact(self, properties: Dict) -> Optional[str]:
        """Actualiza un contacto existente"""
        response = requests.patch(
            f"{self.url}/{self.contact_id}",
            headers=self.headers,
            json={"properties": properties}
        )
        if response.status_code == 200:
            logging.info(f"Contacto actualizado exitosamente: {self.contact_id}")
            logging.info(f"Propiedades actualizadas: {properties}")
            return self.contact_id
        
        logging.error(f"Error actualizando contacto {self.contact_id}: {response.status_code}")
        logging.error(f"Respuesta de HubSpot: {response.text}")
        logging.error(f"Propiedades que se intentaron actualizar: {properties}")
        return None
    
    # Eliminar contacto (usado para el comando de reset)
    def delete_contact(self) -> Optional[str]:
        """Elimina un contacto"""
        try:
            response = requests.delete(
                f"{self.url}/{self.contact_id}",
                headers=self.headers
            )
            if response.status_code == 204:
                logging.info(f"Contacto eliminado exitosamente: {self.contact_id}")
                return self.contact_id
            logging.error(f"Error eliminando contacto: {response.status_code}")
            logging.error(f"Respuesta de HubSpot: {response.text}")
            return None
        except Exception as e:
            logging.error(f"Error eliminando contacto: {e}")
            return None