"""
Test de Coincidencia de Especificaciones de Inventario (Integración Conversacional)

Este archivo prueba si el chatbot recomienda correctamente las máquinas basándose en 
los requerimientos del usuario, utilizando el flujo conversacional completo.

Se simula una conversación donde el usuario:
1. Se identifica (nombre)
2. Indica el tipo de maquinaria
3. Proporciona especificaciones (altura, potencia, capacidad, etc.)
4. El bot recomienda máquinas

Los tests verifican que la primera máquina recomendada sea la más cercana a los 
requerimientos del usuario (gracias al ordenamiento por relevancia).

Tipos testeados:
- soldadora: amperaje_amps_max, tipo_alimentacion (2 tests: 300A y 180A)
- compresor: tipo_compresor, caudal_cfm_max (4 tests: 200 CFM, 500 CFM, 100 CFM, 750 CFM portátil)
- generador: potencia_kw (3 tests: 20kW, 5kW, 100kW)
- torre_iluminacion: tipo_reflector
- montacargas: capacidad_carga_kg
- plataforma: tipo_plataforma, altura_trabajo_m, tipo_alimentacion (3 tests)
- manipulador: altura_maxima_m, capacidad_carga_kg
"""

import os
import json
import sys
import time
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

from dotenv import load_dotenv
load_dotenv()

from azure.cosmos import CosmosClient
from ai_langchain import IntelligentLeadQualificationChatbot, AzureOpenAIConfig
from check_guardrails import ContentSafetyGuardrails
from maquinaria_config import machinery_config_service

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

def setup_chatbot() -> IntelligentLeadQualificationChatbot:
    """Configura y devuelve una instancia del chatbot con conexión a Cosmos DB."""
    if "FOUNDRY_ENDPOINT" not in os.environ or "FOUNDRY_API_KEY" not in os.environ:
        print("\n❌ ERROR: Variables de entorno FOUNDRY no encontradas.")
        exit()

    cosmos_client = None
    db_name = None
    
    if "COSMOS_CONNECTION_STRING" in os.environ and "COSMOS_DB_NAME" in os.environ:
        try:
            print("🔌 Conectando a Cosmos DB...")
            cosmos_client = CosmosClient.from_connection_string(os.environ["COSMOS_CONNECTION_STRING"])
            db_name = os.environ["COSMOS_DB_NAME"]
            machinery_config_service.__init__(cosmos_client, db_name)
            print("✅ Conexión a Cosmos DB exitosa.")
        except Exception as e:
            raise RuntimeError(f"Error conectando a Cosmos DB: {e}")
    else:
        raise RuntimeError("Variables COSMOS_CONNECTION_STRING y COSMOS_DB_NAME requeridas")

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
    return s.replace(" ", "_")

def _get_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%H:%M:%S") + f".{now.microsecond // 10000:02d}"

def _extract_recommended_machines(response: str) -> List[str]:
    """Extrae los modelos de máquinas recomendados de la respuesta del bot."""
    machines = []
    # Buscar líneas que empiecen con "- " seguido de un modelo
    pattern = r"^- (.+?)(?:\s*\(|$|\n)"
    matches = re.findall(pattern, response, re.MULTILINE)
    for match in matches:
        # Limpiar el nombre del modelo
        modelo = match.strip()
        if modelo:
            machines.append(modelo)
    return machines

# ============================================================================
# DEFINICIÓN DE TESTS CONVERSACIONALES
# ============================================================================

# Cada test define:
# - name: Nombre descriptivo del test
# - conversation_flow: Lista de mensajes del usuario
# - expected_first_machine: Modelo que debería aparecer primero en recomendaciones
# - description: Descripción del test

CONVERSATIONAL_TESTS = [
    # --------------------------------------------------------------------
    # SOLDADORA (2 campos)
    # --------------------------------------------------------------------
    {
        "name": "Soldadora 300A combustible",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado y busco una soldadora",
            "De 300 amperes",
            "combustible"
        ],
        "expected_first_machine": "Shindaiwa DGW340DM",
        "description": "Debería recomendar DGW340DM (340A) como la más cercana a 300A"
    },
    {
        "name": "Soldadora 180A combustible (baja potencia)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado y busco una soldadora",
            "De 180 amperes",
            "combustible"
        ],
        "expected_first_machine": "Shindaiwa EGW185MS",
        "description": "Debería recomendar EGW185MS (185A, el más cercano a 180A)"
    },
    
    # --------------------------------------------------------------------
    # COMPRESOR (2 campos)
    # --------------------------------------------------------------------
    {
        "name": "Compresor 200 CFM 100 PSI",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito un compresor",
            "200 CFM",
            "100 PSI"
        ],
        "expected_first_machine": None,  # Validar que recomiende algo
        "min_recommendations": 1,
        "description": "Debería recomendar compresores con >=200 CFM y >=100 PSI"
    },
    {
        "name": "Compresor 500 CFM 100 PSI (alta capacidad)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito un compresor",
            "500 CFM",
            "100 PSI"
        ],
        "expected_first_machine": "AIRMAN SAS75VD-E",
        "description": "Debería recomendar SAS75VD-E (501.47 CFM, el más cercano a 500 CFM)"
    },
    {
        "name": "Compresor 100 CFM 100 PSI (baja capacidad)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito un compresor",
            "100 CFM",
            "100 PSI"
        ],
        "expected_first_machine": "AIRMAN SAS22RD6E",
        "description": "Debería recomendar SAS22RD6E (144.79 CFM, el más cercano a 100 CFM)"
    },
    {
        "name": "Compresor 750 CFM 100 PSI (portátil alta capacidad)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito un compresor",
            "750 CFM",
            "100 PSI"
        ],
        "expected_first_machine": "AIRMAN PDS750S-4B1",
        "description": "Debería recomendar PDS750S-4B1 (750 CFM portátil)"
    },
    
    # --------------------------------------------------------------------
    # GENERADOR (2 campos) - Test estacionario
    # --------------------------------------------------------------------
    {
        "name": "Generador 20kW",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado y busco un generador",
            "20 kW"
        ],
        "expected_first_machine": "Shindaiwa DGM250MK-D",
        "description": "Debería recomendar DGM250MK-D (exactamente 20kW)"
    },
    
    # --------------------------------------------------------------------
    # GENERADOR (2 campos) - Test portátil
    # --------------------------------------------------------------------
    {
        "name": "Generador 5kW",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado y busco un generador",
            "5 kW"
        ],
        "expected_first_machine": "Koshin GV-8000S",
        "description": "Debería recomendar GV-8000S (7.2kW, el más cercano a 5kW)"
    },
    
    # --------------------------------------------------------------------
    # GENERADOR (2 campos) - Test estacionario alta potencia
    # --------------------------------------------------------------------
    {
        "name": "Generador 100kW (alta potencia)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado y busco un generador",
            "100 kW"
        ],
        "expected_first_machine": "AIRMAN SDG150S",
        "description": "Debería recomendar SDG150S (120kW, el más cercano a 100kW)"
    },
    
    # --------------------------------------------------------------------
    # TORRE DE ILUMINACIÓN (1 campo)
    # --------------------------------------------------------------------
    {
        "name": "Torre iluminación LED",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Busco torre de iluminación",
            "Que sea LED"
        ],
        "expected_first_machine": None,  # Cualquier torre LED es válida
        "min_recommendations": 1,
        "description": "Debería recomendar torres con reflector LED"
    },
    
    # --------------------------------------------------------------------
    # MONTACARGAS (1 campo)
    # --------------------------------------------------------------------
    {
        "name": "Montacargas 2000kg",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Quiero un montacargas",
            "Capacidad 2000 kg"
        ],
        "expected_first_machine": "LGMG CPD25",
        "description": "Debería recomendar CPD25 (2500kg, el más cercano a 2000kg)"
    },
    
    # --------------------------------------------------------------------
    # PLATAFORMA (4 campos) - Articulada eléctrica 11m
    # --------------------------------------------------------------------
    {
        "name": "Plataforma articulada 11m eléctrica (caso original)",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito una plataforma",
            "Articulada",
            "Altura de trabajo 11m",
            "Altura de plataforma 9m",
            "electrica"  # Sin acento ni mayúscula para coincidir con inventario
        ],
        "expected_first_machine": "LGMG A30JE",
        "description": "CASO CRÍTICO: Debería recomendar A30JE (exactamente 11m/9m)"
    },
    
    # --------------------------------------------------------------------
    # PLATAFORMA (4 campos) - Articulada combustible 18m
    # --------------------------------------------------------------------
    {
        "name": "Plataforma articulada 18m combustible",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito una plataforma",
            "Articulada",
            "Altura de trabajo 18m",
            "Altura de plataforma 16m",
            "Combustible"
        ],
        "expected_first_machine": "LGMG AR60J-2",
        "description": "Debería recomendar AR60J-2 (20.12m/18.12m combustible)"
    },
    
    # --------------------------------------------------------------------
    # PLATAFORMA (4 campos) - Tijera eléctrica 10m
    # --------------------------------------------------------------------
    {
        "name": "Plataforma tijera 10m eléctrica",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Necesito una plataforma",
            "Tijera",
            "Altura de trabajo 10m",
            "Altura de plataforma 8m",
            "electrica"  # Sin acento para coincidir con inventario
        ],
        "expected_first_machine": "LGMG S2632E II",
        "description": "Debería recomendar S2632E II (exactamente 10m/8m tijera)"
    },
    
    # --------------------------------------------------------------------
    # MANIPULADOR (2 campos)
    # --------------------------------------------------------------------
    {
        "name": "Manipulador 6m 2500kg",
        "conversation_flow": [
            "Hola, soy Daniel Maldonado. Busco manipulador telescópico",
            "6 metros de altura",
            "2500 kg"
        ],
        "expected_first_machine": "LGMG H735",
        "description": "Debería recomendar H735 (7m/3500kg, el más cercano)"
    },
]

# ============================================================================
# FUNCIÓN DE EJECUCIÓN DE TESTS
# ============================================================================

def run_single_test(
    chatbot: IntelligentLeadQualificationChatbot,
    guardrails: ContentSafetyGuardrails,
    test: Dict[str, Any]
) -> Tuple[bool, List[str], List[str]]:
    """
    Ejecuta un test individual y retorna (passed, output_lines, recommended_machines).
    """
    output_lines: List[str] = []
    chatbot.reset_conversation()
    
    output_lines.append("-" * 70)
    output_lines.append(f"📋 TEST: {test['name']}")
    output_lines.append(f"   Descripción: {test['description']}")
    output_lines.append("")
    
    last_response = ""
    recommended_machines: List[str] = []
    
    for msg in test["conversation_flow"]:
        time.sleep(1.5)  # Rate limiting
        
        ts = _get_timestamp()
        output_lines.append(f"[{ts}] 👤 Usuario: {msg}")
        
        # Guardrails check
        safety_result = guardrails.check_message_safety(msg)
        if safety_result:
            ts = _get_timestamp()
            output_lines.append(f"[{ts}] ❌ Bot (Guardrails): {safety_result['message']}")
            continue
        
        # Enviar mensaje al bot
        response = chatbot.send_message(msg)
        last_response = response
        ts = _get_timestamp()
        output_lines.append(f"[{ts}] 🤖 Bot: {response}\n")
        
        # Intentar extraer recomendaciones de cada respuesta
        machines = _extract_recommended_machines(response)
        if machines:
            recommended_machines = machines
    
    # Evaluar resultado
    output_lines.append("   📊 Evaluación:")
    
    passed = True
    
    if recommended_machines:
        output_lines.append(f"   Máquinas recomendadas: {', '.join(recommended_machines[:3])}")
        
        # Verificar primera recomendación
        if test.get("expected_first_machine"):
            if recommended_machines[0] == test["expected_first_machine"]:
                output_lines.append(f"   ✓ Primera recomendación correcta: {recommended_machines[0]}")
            else:
                output_lines.append(f"   ⚠️ Primera recomendación: {recommended_machines[0]}")
                output_lines.append(f"      Esperada: {test['expected_first_machine']}")
                # Solo fallar si es un test crítico (no marcado con min_recommendations)
                if "min_recommendations" not in test:
                    passed = False
        
        # Verificar mínimo de recomendaciones
        min_recs = test.get("min_recommendations", 1)
        if len(recommended_machines) < min_recs:
            output_lines.append(f"   ❌ Se esperaban al menos {min_recs} recomendaciones")
            passed = False
    else:
        # Verificar si se esperaban recomendaciones
        if test.get("expected_first_machine") or test.get("min_recommendations", 0) > 0:
            output_lines.append("   ❌ No se encontraron recomendaciones en la respuesta")
            output_lines.append(f"   Última respuesta: {last_response[:200]}...")
            passed = False
        else:
            output_lines.append("   ⚠️ No se esperaban recomendaciones específicas")
    
    if passed:
        output_lines.append("   ✅ PASÓ")
    else:
        output_lines.append("   ❌ FALLÓ")
    
    output_lines.append("")
    
    return passed, output_lines, recommended_machines

def run_all_tests(test_indices: Optional[List[int]] = None):
    """
    Ejecuta los tests conversacionales.
    
    Args:
        test_indices: Lista opcional de índices (1-indexed) de tests a ejecutar.
                     Si es None, ejecuta todos los tests.
    """
    print("🚀 Iniciando tests conversacionales de especificaciones de inventario...\n")
    
    chatbot = setup_chatbot()
    guardrails = ContentSafetyGuardrails()
    
    # Filtrar tests si se especificaron índices
    if test_indices:
        # Convertir a 0-indexed y validar
        valid_indices = []
        for idx in test_indices:
            if 1 <= idx <= len(CONVERSATIONAL_TESTS):
                valid_indices.append(idx - 1)  # Convert to 0-indexed
            else:
                print(f"⚠️  Índice {idx} fuera de rango (1-{len(CONVERSATIONAL_TESTS)})")
        
        if not valid_indices:
            print("❌ No hay tests válidos para ejecutar.")
            return 0, 0
        
        tests_to_run = [(i, CONVERSATIONAL_TESTS[i]) for i in valid_indices]
        print(f"📋 Ejecutando tests seleccionados: {[i+1 for i, _ in tests_to_run]}\n")
    else:
        tests_to_run = list(enumerate(CONVERSATIONAL_TESTS))
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    all_output: List[str] = []
    
    all_output.append("=" * 70)
    all_output.append("🔍 TEST CONVERSACIONAL DE ESPECIFICACIONES DE INVENTARIO")
    all_output.append("=" * 70)
    all_output.append(f"Fecha/Hora: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if test_indices:
        all_output.append(f"Tests seleccionados: {[i+1 for i, _ in tests_to_run]} de {len(CONVERSATIONAL_TESTS)} totales")
    else:
        all_output.append(f"Total de tests: {len(CONVERSATIONAL_TESTS)}")
    all_output.append("")
    
    passed_count = 0
    failed_count = 0
    results_summary: List[Dict[str, Any]] = []
    
    for step, (original_idx, test) in enumerate(tests_to_run, 1):
        test_num = original_idx + 1  # 1-indexed for display
        print(f"▶️  Ejecutando ({step}/{len(tests_to_run)}) Test #{test_num}: {test['name']}")
        
        passed, output_lines, machines = run_single_test(chatbot, guardrails, test)
        all_output.extend(output_lines)
        
        if passed:
            passed_count += 1
            print(f"   ✅ PASÓ")
        else:
            failed_count += 1
            print(f"   ❌ FALLÓ")
        
        results_summary.append({
            "test_num": test_num,
            "name": test["name"],
            "passed": passed,
            "expected": test.get("expected_first_machine"),
            "got": machines[0] if machines else None
        })
    
    # Resumen final
    all_output.append("=" * 70)
    all_output.append("📊 RESUMEN DE RESULTADOS")
    all_output.append("=" * 70)
    all_output.append(f"   Tests ejecutados: {len(tests_to_run)}")
    all_output.append(f"   ✅ Pasados: {passed_count}")
    all_output.append(f"   ❌ Fallados: {failed_count}")
    all_output.append("")
    
    # Detalle por test
    all_output.append("Detalle:")
    for r in results_summary:
        status = "✅" if r["passed"] else "❌"
        if r["expected"]:
            match = "✓" if r["got"] == r["expected"] else f"⚠ Got: {r['got']}"
            all_output.append(f"   {status} #{r['test_num']} {r['name']}: {match}")
        else:
            all_output.append(f"   {status} #{r['test_num']} {r['name']}")
    
    all_output.append("")
    if failed_count == 0:
        all_output.append("🎉 ¡TODOS LOS TESTS PASARON!")
    else:
        all_output.append(f"⚠️ {failed_count} test(s) fallaron.")
    all_output.append("=" * 70)
    
    # Guardar resultados
    out_dir = os.path.join(os.path.dirname(__file__), "test_results")
    os.makedirs(out_dir, exist_ok=True)
    filename = f"test_inventory_match_conversational_{timestamp}.txt"
    filepath = os.path.join(out_dir, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(all_output))
    
    # Imprimir resumen en consola
    print("\n" + "=" * 50)
    print(f"📊 RESUMEN: {passed_count}/{len(tests_to_run)} tests pasados")
    if failed_count == 0:
        print("🎉 ¡TODOS LOS TESTS PASARON!")
    print(f"📁 Resultados: {filepath}")
    print("=" * 50)
    
    return passed_count, failed_count

# ============================================================================
# PUNTO DE ENTRADA
# ============================================================================

if __name__ == "__main__":
    # Parse optional test indices from command line
    # Usage: python test_inventory_match_specifications.py "1,3,5"
    test_indices = None
    
    if len(sys.argv) > 1:
        try:
            # Parse comma-separated indices (e.g., "1,3,5")
            indices_str = sys.argv[1]
            test_indices = [int(x.strip()) for x in indices_str.split(",")]
            print(f"🎯 Ejecutando tests específicos: {test_indices}")
        except ValueError:
            print(f"❌ Error: Argumento inválido '{sys.argv[1]}'")
            print("   Uso: python test_inventory_match_specifications.py \"1,3,5\"")
            print(f"   Rango válido: 1-{len(CONVERSATIONAL_TESTS)}")
            exit(1)
    
    passed, failed = run_all_tests(test_indices)
    exit(0 if failed == 0 else 1)

