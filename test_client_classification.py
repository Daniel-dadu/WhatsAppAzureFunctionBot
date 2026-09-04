import os

os.environ.setdefault("FOUNDRY_API_KEY", "test-key")
os.environ.setdefault("FOUNDRY_ENDPOINT", "https://example.invalid")

from ai_langchain import _sanitize_extracted_info


def test_negative_sales_answer_maps_to_final_customer():
    sanitized = _sanitize_extracted_info(
        {"tipo_cliente": "No tiene"},
        "No me dedico a la venta o renta, es para uso de trabajo constructivo.",
        "¿Te dedicas a la venta o renta de maquinaria?",
        {},
    )

    assert sanitized["tipo_cliente"] == "cliente_final"


def test_negative_usage_question_maps_to_final_customer():
    sanitized = _sanitize_extracted_info(
        {"tipo_cliente": "No tiene"},
        "No, es para nuestra empresa.",
        "¿El equipo es para venta o para uso propio?",
        {},
    )

    assert sanitized["tipo_cliente"] == "cliente_final"


def test_no_certificate_keeps_no_tiene_value():
    sanitized = _sanitize_extracted_info(
        {"constancia_fiscal_entregada": "No tiene"},
        "No cuento con la constancia.",
        "¿Puedes compartir tu Constancia de Situación Fiscal?",
        {"tipo_cliente": "distribuidor"},
    )

    assert sanitized["constancia_fiscal_entregada"] == "No tiene"
