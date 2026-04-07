"""
Test for PDF Quotation Service

Generates a sample quotation PDF to verify the layout and content.
Output: test_results/test_cotizacion.pdf
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pdf_service import QuotationPDFGenerator


def test_generate_quotation_pdf():
    """Generate a sample PDF with mock data and save to test_results/."""
    
    print("🔧 Initializing PDF generator...")
    generator = QuotationPDFGenerator()
    
    # Mock conversation state (simulating a completed conversation)
    mock_state = {
        "nombre": "Carlos Ramírez",
        "apellido": "Ramírez",
        "tipo_maquinaria": "plataforma",
        "maquina_seleccionada": "LGMG S1932EII",
        "quiere_cotizacion": True,
        "nombre_empresa": "Constructora Norte SA de CV",
        "giro_empresa": "construcción",
        "lugar_requerimiento": "Nuevo León",
        "uso_empresa_o_venta": "uso empresa",
        "correo": "carlos@connorte.com",
        "telefono": "81 1234 5678",
        "detalles_maquinaria": {
            "tipo_plataforma": "tijera",
            "altura_trabajo_m": "7",
            "tipo_alimentacion": "eléctrica"
        }
    }
    
    # Mock price info (simulating what pricing_service would return)
    mock_price_info = {
        "price": 8500.00,
        "currency": "USD"
    }
    
    print("📝 Generating PDF...")
    pdf_bytes = generator.generate(mock_state, mock_price_info)
    
    # Verify PDF is valid
    assert len(pdf_bytes) > 0, "PDF is empty!"
    assert pdf_bytes[:5] == b"%PDF-", f"Invalid PDF header: {pdf_bytes[:10]}"
    
    # Save to test_results/
    out_dir = os.path.join(os.path.dirname(__file__), "test_results")
    os.makedirs(out_dir, exist_ok=True)
    
    filepath = os.path.join(out_dir, "test_cotizacion.pdf")
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"✅ PDF generated successfully!")
    print(f"   Size: {len(pdf_bytes):,} bytes")
    print(f"   Saved to: {filepath}")
    print(f"\n📂 Open the file to visually inspect the layout.")


def test_generate_without_price():
    """Generate a PDF without price info (testing 'A consultar' case)."""
    
    print("\n🔧 Testing PDF without price...")
    generator = QuotationPDFGenerator()
    
    mock_state = {
        "nombre": "María López",
        "apellido": "López",
        "tipo_maquinaria": "generador",
        "maquina_seleccionada": "Shindaiwa DGM250MK-D",
        "quiere_cotizacion": True,
        "nombre_empresa": "IndustrialMex",
        "giro_empresa": "manufactura",
        "lugar_requerimiento": "Querétaro",
        "uso_empresa_o_venta": "uso empresa",
        "correo": "maria@industrialmex.com",
        "telefono": "442 111 2233",
    }
    
    pdf_bytes = generator.generate(mock_state, price_info=None)
    
    assert len(pdf_bytes) > 0, "PDF is empty!"
    assert pdf_bytes[:5] == b"%PDF-"
    
    filepath = os.path.join(os.path.dirname(__file__), "test_results", "test_cotizacion_sin_precio.pdf")
    with open(filepath, "wb") as f:
        f.write(pdf_bytes)
    
    print(f"✅ PDF (no price) generated successfully!")
    print(f"   Size: {len(pdf_bytes):,} bytes")
    print(f"   Saved to: {filepath}")


if __name__ == "__main__":
    test_generate_quotation_pdf()
    test_generate_without_price()
    print("\n🎉 All PDF tests passed!")
