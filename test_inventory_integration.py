import os
import json
import time
import re
from datetime import datetime
from typing import List, Dict, Any
from dotenv import load_dotenv

from azure.cosmos import CosmosClient
# Import bot classes
from ai_langchain import IntelligentLeadQualificationChatbot, AzureOpenAIConfig
from check_guardrails import ContentSafetyGuardrails
from maquinaria_config import machinery_config_service

load_dotenv()

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

def setup_chatbot() -> IntelligentLeadQualificationChatbot:
    if "FOUNDRY_ENDPOINT" not in os.environ or "FOUNDRY_API_KEY" not in os.environ:
        print("\n❌ ERROR: Variables de entorno no encontradas.")
        exit()

    # Configurar Cosmos DB
    cosmos_client = None
    db_name = None
    if "COSMOS_CONNECTION_STRING" in os.environ and "COSMOS_DB_NAME" in os.environ:
        try:
            print("🔌 Conectando a Cosmos DB...")
            cosmos_client = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION_STRING"])
            db_name = os.environ["COSMOS_DB_NAME"]
            
            # Re-inicializar servicios globales con el cliente
            machinery_config_service.__init__(cosmos_client, db_name)
            print("✅ Conexión a Cosmos DB exitosa.")
        except Exception as e:
            print(f"⚠️ Error conectando a Cosmos DB: {e}")
            print("⚠️ Se usará inventario local (fallback).")

    azure_config = AzureOpenAIConfig(
        endpoint=os.getenv("FOUNDRY_ENDPOINT"),
        api_key=os.getenv("FOUNDRY_API_KEY"),
        deployment_name="gpt-4.1-mini",
        api_version="2024-12-01-preview",
        model_name="gpt-4.1-mini"
    )
    
    return IntelligentLeadQualificationChatbot(azure_config, cosmos_client=cosmos_client, db_name=db_name)

def _sanitize_filename(name: str) -> str:
    s = re.sub(r"[^\w\-_. ]", "_", name)
    s = s.replace(" ", "_")
    return s

def _get_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 10000:02d}"

# ============================================================================
# FLUJOS DE PRUEBA
# ============================================================================

MACHINERY_FLOWS = {
    "Soldadora": [
        "Hola, soy Daniel Maldonado y busco una soldadora",
        "De 300 amperes",
        "combustible"
    ],
    "Compresor": [
        "Hola, soy Daniel Maldonado. Necesito un compresor",
        "185 CFM",
        "100 PSI"
    ],
    "Rompedor": [
        "Hola, soy Daniel Maldonado. Quiero un rompedor"
    ],
    "Generador": [
        "Hola, soy Daniel Maldonado y busco un generador",
        "Portatil",
        "20 kW"
    ],
    "Torre de Iluminación": [
        "Hola, soy Daniel Maldonado. Busco torre de iluminación",
        "Que sea LED"
    ],
    "Plataforma": [
        "Hola, soy Daniel Maldonado. Necesito una plataforma",
        "Articulada",
        "Altura 15m",
        "Electrica"
    ],
    "Montacargas": [
        "Hola, soy Daniel Maldonado. Quiero un montacargas",
        "Capacidad 3000 kg"
    ],
    "Manipulador Tel": [
        "Hola, soy Daniel Maldonado. Busco manipulador telescopico",
        "10 metros",
        "3000 kg"
    ],
    "Motobomba": [
        "Hola, soy Daniel Maldonado. Necesito una motobomba"
    ],
    "Apisonador": [
        "Hola, soy Daniel Maldonado. Busco un apisonador"
    ],
    "Cortadora de Varilla": [
        "Hola, soy Daniel Maldonado. Busco cortadora de varilla"
    ],
    "Dobladora de Varilla": [
        "Hola, soy Daniel Maldonado. Busco dobladora de varilla"
    ]
}

# ============================================================================
# RUNNER
# ============================================================================

def run_inventory_tests():
    chatbot = setup_chatbot()
    guardrails = ContentSafetyGuardrails()
    
    output_lines = []
    output_lines.append("==================================================")
    output_lines.append("🤖  TEST DE RECOMENDACIONES DE INVENTARIO")
    output_lines.append("==================================================\n")

    print("🚀 Iniciando pruebas de inventario...")

    for machine_name, flow_messages in MACHINERY_FLOWS.items():
        test_title = f"Prueba: {machine_name}"
        print(f"▶️  Ejecutando: {test_title}")
        
        output_lines.append(f"--- INICIANDO PRUEBA: {test_title} ---\n")
        
        # Resetear estado para cada prueba
        chatbot.reset_conversation()
        
        for msg in flow_messages:
            # Simular delay humano
            time.sleep(1)
            
            ts = _get_timestamp()
            output_lines.append(f"[{ts}] 👤 Usuario: {msg}")
            
            # Guardrails check (opcional pero realista)
            safety_result = guardrails.check_message_safety(msg)
            if safety_result:
                ts = _get_timestamp()
                output_lines.append(f"[{ts}] ❌ Bot (Guardrails): {safety_result['message']}")
                continue

            # Enviar mensaje al bot
            response = chatbot.send_message(msg)
            ts = _get_timestamp()
            output_lines.append(f"[{ts}] 🤖 Bot: {response}\n")
        
        output_lines.append("-" * 40 + "\n")

    # Guardar reporte
    out_dir = os.path.join(os.path.dirname(__file__), "test_results")
    os.makedirs(out_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"test_inventory_conversations_{timestamp}.txt"
    filepath = os.path.join(out_dir, filename)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
        
    print(f"\n✅ Pruebas finalizadas. Reporte guardado en: {filepath}")

if __name__ == "__main__":
    run_inventory_tests()
