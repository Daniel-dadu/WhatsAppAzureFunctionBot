"""
Tests para la identidad de Alpha C y la detección de leads fuera de cobertura.

Caso real que originó esto (real_conversations_withLeads/5.json): un lead con
número de Venezuela preguntó "¿están ubicados en Venezuela?" y el bot respondió
"estamos ubicados en Venezuela". Alpha C solo opera en México.

No requieren llamadas al LLM: la detección es determinista.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ai_langchain import (
    AzureOpenAIConfig,
    IntelligentLeadQualificationChatbot,
    IntelligentResponseGenerator,
)
from company_profile import (
    COMPANY_COUNTRY,
    build_company_facts,
    build_coverage_disclaimer,
    build_coverage_instruction,
    country_from_wa_id,
    evaluate_coverage,
    foreign_country_in_text,
    is_mexican_state,
)
from inventory_service import InventoryService


# ============================================================================
# PAÍS A PARTIR DEL NÚMERO
# ============================================================================

@pytest.mark.parametrize("wa_id, esperado", [
    ("584241385150", "Venezuela"),      # el lead de 5.json
    ("5213336612004", "México"),        # celular mexicano (521)
    ("528112345678", "México"),
    ("573001234567", "Colombia"),
    ("5491123456789", "Argentina"),
    ("5071234567", "Panamá"),           # lada de 3 dígitos, no debe leerse como "50"
    ("14155552671", "Estados Unidos o Canadá"),
    ("9991234567", None),               # lada desconocida
    ("", None),
    (None, None),
])
def test_pais_desde_el_numero(wa_id, esperado):
    assert country_from_wa_id(wa_id) == esperado


# ============================================================================
# LUGAR DEL REQUERIMIENTO
# ============================================================================

@pytest.mark.parametrize("lugar, es_mexicano", [
    ("Jalisco", True),
    ("en la Ciudad de México", True),
    ("Monterrey Nuevo León", True),
    ("pto Ordaz Edo Bolívar", False),
    ("", False),
    (None, False),
])
def test_estado_mexicano(lugar, es_mexicano):
    assert is_mexican_state(lugar) is es_mexicano


def test_pais_extranjero_en_texto():
    assert foreign_country_in_text("lo necesito en Venezuela") == "Venezuela"
    assert foreign_country_in_text("para Guadalajara") is None


# ============================================================================
# COBERTURA
# ============================================================================

def test_lead_de_venezuela_esta_fuera_de_cobertura():
    """El caso de 5.json: número +58 y requerimiento en Puerto Ordaz."""
    coverage = evaluate_coverage("584241385150", "pto Ordaz Edo Bolívar")
    assert coverage.fuera_de_mexico is True
    assert coverage.pais == "Venezuela"
    assert coverage.motivo == "telefono"


def test_lead_mexicano_no_se_marca():
    assert evaluate_coverage("5213336612004", "Jalisco").fuera_de_mexico is False
    assert evaluate_coverage("5213336612004", None).fuera_de_mexico is False


def test_el_lugar_manda_sobre_la_lada():
    """
    Un número extranjero que pide el equipo para México SÍ está en cobertura, y
    un número mexicano que lo pide para fuera, no.
    """
    assert evaluate_coverage("584241385150", "Monterrey Nuevo León").fuera_de_mexico is False
    fuera = evaluate_coverage("5215512345678", "lo necesito en Venezuela")
    assert fuera.fuera_de_mexico is True
    assert fuera.motivo == "lugar"


@pytest.mark.parametrize("wa_id, lugar", [
    ("9991234567", None),        # lada que no reconocemos
    (None, None),
    ("5213336612004", "Tepatitlán"),  # ciudad mexicana que no es un estado
])
def test_sin_señal_clara_no_se_marca_fuera_de_cobertura(wa_id, lugar):
    """
    Decirle a un lead mexicano que no lo atendemos es mucho peor que callar:
    ante la duda, se le trata como si estuviera en México.
    """
    assert evaluate_coverage(wa_id, lugar).fuera_de_mexico is False


# ============================================================================
# TEXTO PARA EL PROMPT
# ============================================================================

def test_identidad_niega_otros_paises():
    facts = build_company_facts()
    assert COMPANY_COUNTRY in facts
    assert "NO tenemos sucursales" in facts
    # Lo que dijo el bot en 5.json y no debe volver a decir
    assert "estamos ubicados para atenderte" in facts.lower()


def test_instruccion_de_cobertura_no_corta_la_conversacion():
    instruccion = build_coverage_instruction(
        evaluate_coverage("584241385150", "pto Ordaz Edo Bolívar")
    )
    assert "Venezuela" in instruccion
    assert "NO cortes la conversación" in instruccion
    assert "PROHIBIDO prometer envíos" in instruccion


def test_sin_instruccion_para_lead_mexicano():
    coverage = evaluate_coverage("5213336612004", "Jalisco")
    assert build_coverage_instruction(coverage) == ""
    assert build_coverage_disclaimer(coverage) == ""


# ============================================================================
# EFECTO EN EL FLUJO
# ============================================================================

@pytest.fixture
def chatbot():
    """Chatbot con credenciales dummy: estas pruebas no invocan al LLM."""
    config = AzureOpenAIConfig(
        endpoint="https://dummy.openai.azure.com/",
        api_key="dummy-key",
        deployment_name="dummy",
    )
    bot = IntelligentLeadQualificationChatbot(config)
    bot.load_conversation("584241385150")
    return bot


def test_el_chatbot_ubica_al_lead_por_su_wa_id(chatbot):
    coverage = chatbot._evaluate_lead_coverage()
    assert coverage.fuera_de_mexico is True
    assert coverage.pais == "Venezuela"


def test_la_aclaracion_se_da_una_sola_vez(chatbot):
    """
    Se le sigue calificando igual; solo no queremos repetirle en cada mensaje
    que no operamos en su país.
    """
    generator = IntelligentResponseGenerator.__new__(IntelligentResponseGenerator)
    generator.inventory_service = InventoryService()

    state = dict(chatbot.state)
    state.update({
        "nombre": "Franklin",
        "tipo_maquinaria": "rompedor",
        "detalles_maquinaria": {"peso_kg": 30},
        "marcas_solicitadas": [],
        "marcas_aclaradas": True,
        "cobertura_aclarada": False,
    })
    coverage = chatbot._evaluate_lead_coverage()

    primera = generator.generate_response(
        "Franklin Conquista", [], {}, state,
        next_question="¿Te gustaría recibir una cotización?",
        question_type="quiere_cotizacion", coverage=coverage,
    )
    assert "solo provee maquinaria dentro de México" in primera
    assert state["cobertura_aclarada"] is True

    segunda = generator.generate_response(
        "sí", [], {}, state,
        next_question="¿Te gustaría recibir una cotización?",
        question_type="quiere_cotizacion", coverage=coverage,
    )
    assert "solo provee maquinaria dentro de México" not in segunda
