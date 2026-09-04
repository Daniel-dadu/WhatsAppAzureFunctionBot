import os

os.environ.setdefault("FOUNDRY_API_KEY", "test-key")
os.environ.setdefault("FOUNDRY_ENDPOINT", "https://example.invalid")

from ai_langchain import _build_unit_clarification_response, _sanitize_extracted_info
from check_guardrails import ContentSafetyGuardrails


def test_semicolon_alone_is_not_code_injection():
    guardrails = ContentSafetyGuardrails.__new__(ContentSafetyGuardrails)

    assert not guardrails.detect_code_injection(
        "No sé los CFM; me dijeron que debe tener capacidad de 5000 litros."
    )


def test_semicolon_does_not_hide_actual_sql_injection():
    guardrails = ContentSafetyGuardrails.__new__(ContentSafetyGuardrails)

    assert guardrails.detect_code_injection("dato válido; DROP TABLE users")


def test_liters_are_not_extracted_as_cfm():
    extracted = {
        "detalles_maquinaria": {
            "tipo_compresor": "portátil",
            "caudal_cfm_max": 5000,
        }
    }

    sanitized = _sanitize_extracted_info(
        extracted,
        "Portátil, necesito una capacidad de 5000 litros.",
        "¿Qué tipo de compresor necesitas: portátil o estacionario?",
        {"tipo_maquinaria": "compresor"},
    )

    assert sanitized["detalles_maquinaria"] == {"tipo_compresor": "portátil"}


def test_incompatible_unit_wins_even_when_cfm_is_mentioned():
    extracted = {"detalles_maquinaria": {"caudal_cfm_max": 5000}}

    sanitized = _sanitize_extracted_info(
        extracted,
        "No sé los CFM; solo tengo una capacidad de 5000 litros.",
        "¿Cuánto volumen de aire en CFM necesitas?",
        {"tipo_maquinaria": "compresor"},
    )

    assert "detalles_maquinaria" not in sanitized


def test_explicit_cfm_is_accepted():
    extracted = {"detalles_maquinaria": {"caudal_cfm_max": 200}}

    sanitized = _sanitize_extracted_info(
        extracted,
        "Necesito 200 CFM.",
        None,
        {"tipo_maquinaria": "compresor"},
    )

    assert sanitized["detalles_maquinaria"]["caudal_cfm_max"] == 200


def test_bare_number_is_accepted_as_direct_cfm_answer():
    extracted = {"detalles_maquinaria": {"caudal_cfm_max": 200}}

    sanitized = _sanitize_extracted_info(
        extracted,
        "200",
        "¿Cuánto volumen de aire en CFM necesitas?",
        {"tipo_maquinaria": "compresor"},
    )

    assert sanitized["detalles_maquinaria"]["caudal_cfm_max"] == 200


def test_bare_number_without_unit_context_is_rejected():
    extracted = {"detalles_maquinaria": {"caudal_cfm_max": 200}}

    sanitized = _sanitize_extracted_info(
        extracted,
        "Necesito un compresor de 200.",
        None,
        {"tipo_maquinaria": "compresor"},
    )

    assert "detalles_maquinaria" not in sanitized


def test_incompatible_unit_gets_deterministic_clarification():
    response = _build_unit_clarification_response(
        "No sé los CFM; solo tengo una capacidad de 5000 litros.",
        {
            "tipo_maquinaria": "compresor",
            "detalles_maquinaria": {"tipo_compresor": "portátil"},
        },
    )

    assert response == (
        "Por ahora no puedo convertir otras unidades a CFM. "
        "Para continuar, necesito que me compartas el valor directamente en CFM."
    )


def test_expected_unit_does_not_trigger_clarification():
    response = _build_unit_clarification_response(
        "Necesito 200 CFM.",
        {
            "tipo_maquinaria": "compresor",
            "detalles_maquinaria": {"tipo_compresor": "portátil"},
        },
    )

    assert response is None
