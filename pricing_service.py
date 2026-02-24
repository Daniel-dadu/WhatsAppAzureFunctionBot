"""
Pricing Service

Fetches prices from SQL Server database for machinery products.
Only supports machines that have mappings in model_code_mapping.py
"""

import os
import logging
from typing import Dict, Optional, List
from functools import lru_cache

try:
    import pyodbc
    logging.info("[PRICING_DEBUG] pyodbc imported successfully")
except ImportError:
    pyodbc = None
    logging.error("[PRICING_DEBUG] pyodbc NOT available - ImportError. Pricing service will return None for ALL queries. "
                  "This likely means the ODBC Driver is not installed in the Azure Function environment.")

from model_code_mapping import get_sql_code, has_price_mapping, fuzzy_get_sql_code, fuzzy_has_price_mapping


class PricingService:
    """
    Service for fetching machinery prices from SQL Server.
    
    Only returns prices for machines that have mappings between
    local inventory and SQL database.
    """
    
    def __init__(self):
        """Initialize the pricing service with SQL connection details."""
        self._connection_string = None
        self._price_cache: Dict[str, Optional[dict]] = {}
        self._cache_loaded = False
        
        logging.info("[PRICING_DEBUG] Initializing PricingService...")
        logging.info(f"[PRICING_DEBUG] pyodbc available: {pyodbc is not None}")
        
        # Build connection string from environment variables
        server = os.environ.get('PRICES_SQL_SERVER')
        database = os.environ.get('PRICES_SQL_DATABASE')
        username = os.environ.get('PRICES_SQL_USERNAME')
        password = os.environ.get('PRICES_SQL_PASSWORD')
        
        # Log presence of each env var (without revealing values)
        logging.info(f"[PRICING_DEBUG] Env vars - PRICES_SQL_SERVER: {'SET' if server else 'MISSING'}, "
                     f"PRICES_SQL_DATABASE: {'SET' if database else 'MISSING'}, "
                     f"PRICES_SQL_USERNAME: {'SET' if username else 'MISSING'}, "
                     f"PRICES_SQL_PASSWORD: {'SET' if password else 'MISSING'}")
        
        if all([server, database, username, password]):
            self._connection_string = (
                f"Driver={{ODBC Driver 18 for SQL Server}};"
                f"Server={server};"
                f"Database={database};"
                f"Uid={username};"
                f"Pwd={password};"
                f"Encrypt=yes;"
                f"TrustServerCertificate=yes;"
            )
            logging.info(f"[PRICING_DEBUG] Connection string built successfully. Server: {server}, Database: {database}")
        else:
            logging.error("[PRICING_DEBUG] SQL Server environment variables NOT fully configured. Pricing DISABLED.")
    
    def _load_all_prices(self) -> None:
        """
        Load all prices from SQL Server into cache.
        Called once on first price request.
        """
        if self._cache_loaded:
            logging.info("[PRICING_DEBUG] _load_all_prices: cache already loaded, skipping.")
            return
        if not self._connection_string:
            logging.error("[PRICING_DEBUG] _load_all_prices: NO connection string available. Cannot load prices.")
            return
        if not pyodbc:
            logging.error("[PRICING_DEBUG] _load_all_prices: pyodbc is NOT available. Cannot load prices.")
            return
            
        try:
            logging.info("[PRICING_DEBUG] _load_all_prices: Attempting SQL Server connection...")
            conn = pyodbc.connect(self._connection_string, timeout=30)
            logging.info("[PRICING_DEBUG] _load_all_prices: SQL Server connection SUCCESSFUL")
            cursor = conn.cursor()
            
            # Fetch all products with their prices
            query = """
                SELECT CODIGO, fixed_price, currency_id 
                FROM [dbo].[inventario_odoo_chatbot]
                WHERE fixed_price IS NOT NULL
            """
            logging.info("[PRICING_DEBUG] _load_all_prices: Executing query...")
            cursor.execute(query)
            
            for row in cursor.fetchall():
                codigo = row[0]
                price = row[1]
                currency = row[2] or "USD"
                
                if codigo and price:
                    self._price_cache[codigo] = {
                        "price": float(price),
                        "currency": currency
                    }
            
            conn.close()
            self._cache_loaded = True
            logging.info(f"[PRICING_DEBUG] _load_all_prices: SUCCESS - Loaded {len(self._price_cache)} prices from SQL Server")
            
            # Log a sample of loaded codes for verification
            sample_codes = list(self._price_cache.keys())[:5]
            logging.info(f"[PRICING_DEBUG] _load_all_prices: Sample codes in cache: {sample_codes}")
            
        except Exception as e:
            logging.error(f"[PRICING_DEBUG] _load_all_prices: FAILED to load prices from SQL Server: {type(e).__name__}: {e}")
            import traceback
            logging.error(f"[PRICING_DEBUG] _load_all_prices: Traceback: {traceback.format_exc()}")
            self._cache_loaded = True  # Mark as loaded to avoid repeated failures
    
    def get_price(self, local_model: str) -> Optional[dict]:
        """
        Get the price for a machine by its local model name.
        
        Args:
            local_model: The model name from inventory_data.py (e.g., "AIRMAN SAS75RD6E")
            
        Returns:
            dict with {"price": float, "currency": str} if found, None otherwise
        """
        logging.info(f"[PRICING_DEBUG] get_price called for model: '{local_model}'")
        
        # Check if this model has an exact mapping
        if has_price_mapping(local_model):
            sql_code = get_sql_code(local_model)
            logging.info(f"[PRICING_DEBUG] get_price: EXACT match for '{local_model}' → SQL code '{sql_code}'")
        else:
            # Try fuzzy matching (handles partial names like 'DGM250MK-D' → 'Shindaiwa DGM250MK-D')
            logging.info(f"[PRICING_DEBUG] get_price: No exact match for '{local_model}', trying fuzzy match...")
            full_name, sql_code = fuzzy_get_sql_code(local_model)
            if full_name:
                logging.info(f"[PRICING_DEBUG] get_price: FUZZY match '{local_model}' → '{full_name}' → SQL code '{sql_code}'")
            else:
                logging.info(f"[PRICING_DEBUG] get_price: model '{local_model}' has NO mapping (exact nor fuzzy)")
                return None
        
        if not sql_code:
            logging.info(f"[PRICING_DEBUG] get_price: no SQL code resolved for '{local_model}'")
            return None
        
        # Ensure prices are loaded
        self._load_all_prices()
        
        # Look up in cache
        result = self._price_cache.get(sql_code)
        if result:
            logging.info(f"[PRICING_DEBUG] get_price: FOUND price for '{local_model}' (code={sql_code}): ${result['price']:,.2f} {result['currency']}")
        else:
            logging.warning(f"[PRICING_DEBUG] get_price: NO price found in cache for '{local_model}' (code={sql_code}). "
                          f"Cache has {len(self._price_cache)} entries. Cache loaded: {self._cache_loaded}")
        return result
    
    def get_prices_batch(self, local_models: List[str]) -> Dict[str, Optional[dict]]:
        """
        Get prices for multiple machines at once.
        
        Args:
            local_models: List of model names from inventory_data.py
            
        Returns:
            Dict mapping model name to price info (or None if not found)
        """
        # Ensure prices are loaded
        self._load_all_prices()
        
        results = {}
        for model in local_models:
            results[model] = self.get_price(model)
        
        return results
    
    def is_available(self) -> bool:
        """Check if the pricing service is properly configured."""
        return self._connection_string is not None and pyodbc is not None
    
    def refresh_cache(self) -> None:
        """Clear and reload the price cache."""
        self._price_cache.clear()
        self._cache_loaded = False
        self._load_all_prices()


# Singleton instance for use across the application
_pricing_service_instance: Optional[PricingService] = None


def get_pricing_service() -> PricingService:
    """Get the singleton pricing service instance."""
    global _pricing_service_instance
    if _pricing_service_instance is None:
        _pricing_service_instance = PricingService()
    return _pricing_service_instance
