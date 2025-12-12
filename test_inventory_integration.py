import unittest
from unittest.mock import MagicMock
from maquinaria_config import machinery_config_service
from inventory_service import InventoryService
from ai_langchain import IntelligentResponseGenerator, AzureOpenAIConfig, ConversationState

class TestInventoryIntegration(unittest.TestCase):

    def setUp(self):
        """Reset configs before each test"""
        # Ensure fallback is loaded or manually set for tests
        self.inventory_service = InventoryService()
        if not self.inventory_service.container:
             # Force load if it didn't happen (though it should with the fallback logic)
             from update_invertory_db.inventory_data import inventario
             self.inventory_service._local_inventory_fallback = inventario
        self.config_service = machinery_config_service

    def test_config_service(self):
        """Test getting configuration for a specific type"""
        config = self.config_service.get_config("soldadora")
        self.assertIsNotNone(config)
        self.assertEqual(config.name, "Soldadora")
        field_names = [f.name for f in config.fields]
        self.assertIn("amperaje", field_names)

    def test_inventory_filtering_soldadora(self):
        """Test filtering logic for Soldadora"""
        # Case 1: Amperaje requirement met (>=)
        # inventario has machines undefined in snippet but let's assume standard ones or empty if using real file
        # Since I am using the real 'inventario.py', let's check what's inside.
        # Actually, let's mock the inventory data in the service for strict unit testing
        
        mock_inventory = [
            {"modelo": "Soldadora Small", "categoria": "soldadora", "amperaje": "100 amps"},
            {"modelo": "Soldadora Big", "categoria": "soldadora", "amperaje": "300 amps"},
            {"modelo": "Platform", "categoria": "plataforma"}
        ]
        self.inventory_service._local_inventory_fallback = mock_inventory

        reqs = {"amperaje": "200"}
        matches = self.inventory_service.find_matching_machines("soldadora", reqs)
        
        # Should match "Soldadora Big" (300 >= 200) but not "Soldadora Small" (100 < 200)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["modelo"], "Soldadora Big")

    def test_inventory_filtering_plataforma(self):
        """Test filtering logic for Plataforma"""
        mock_inventory = [
            {"modelo": "Plataforma A", "categoria": "plataforma", "tipo_plataforma": "articulada", "altura_trabajo": "20m"},
            {"modelo": "Plataforma B", "categoria": "plataforma", "tipo_plataforma": "tijera", "altura_trabajo": "10m"},
        ]
        self.inventory_service._local_inventory_fallback = mock_inventory

        # Req: Articulada, 15m
        reqs = {"tipo_plataforma": "articulada", "altura_trabajo": "15"}
        matches = self.inventory_service.find_matching_machines("plataforma", reqs)
        
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["modelo"], "Plataforma A")

    def test_chatbot_integration_response(self):
        """Test that the chatbot generates a response with recommendations"""
        # Mock Azure Config
        mock_config = MagicMock(spec=AzureOpenAIConfig)
        mock_config.create_conversational_llm.return_value = MagicMock()
        
        generator = IntelligentResponseGenerator(mock_config)
        
        # Inject mock service
        # Ensure fallback is used by setting container to None explicitly if needed (it is None by default)
        generator.inventory_service.container = None 
        generator.inventory_service._local_inventory_fallback = [
             {"modelo": "Test Machine", "categoria": "soldadora", "amperaje": "500"}
        ]
        
        state = {
            "nombre": "TestUser",
            "tipo_maquinaria": "soldadora",
            "detalles_maquinaria": {"amperaje": "100"}
        }
        
        response = generator.generate_response(
            message="Si, cotizame", 
            history_messages=[], 
            extracted_info={}, 
            current_state=state, 
            question_type="quiere_cotizacion"
        )
        
        self.assertIn("Test Machine", response)
        self.assertIn("recomiendo", response)

if __name__ == '__main__':
    unittest.main()
