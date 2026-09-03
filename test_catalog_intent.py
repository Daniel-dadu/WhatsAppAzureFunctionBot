import os

import pytest

os.environ.setdefault("FOUNDRY_API_KEY", "test-key")
os.environ.setdefault("FOUNDRY_ENDPOINT", "https://example.invalid")

from ai_langchain import _build_catalog_response, _is_explicit_catalog_request
from maquinaria_config import machinery_config_service


@pytest.mark.parametrize(
    "message",
    [
        "¿Qué máquinas manejan?",
        "¿Cuáles son los equipos que vende Alpha C?",
        "¿Qué tipos de maquinaria tienen?",
        "Muéstrame el catálogo.",
        "¿Qué productos ofrecen?",
    ],
)
def test_explicit_general_catalog_requests_are_detected(message):
    assert _is_explicit_catalog_request(message)


@pytest.mark.parametrize(
    "message",
    [
        "Sí, cotízame esa soldadora.",
        "¿Tienen soldadoras?",
        "¿Qué modelos de generadores manejan?",
        "¿Cuánto cuesta un compresor?",
        "Quiero la primera opción.",
        "Mándame el catálogo de soldadoras.",
    ],
)
def test_specific_product_and_quotation_requests_do_not_trigger_full_catalog(message):
    assert not _is_explicit_catalog_request(message)


def test_catalog_response_contains_every_configured_type_and_pending_question():
    response = _build_catalog_response("¿Con quién tengo el gusto?")

    for display_name in machinery_config_service.get_type_display_list():
        assert display_name in response
    assert "entre otros" not in response.lower()
    assert response.endswith("¿Con quién tengo el gusto?")
