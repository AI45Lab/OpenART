import os
import json
import toml
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

class TransactionConfig:
    """
    Configuration manager for transaction service.
    Loads settings from environment variables, config files (JSON and TOML).
    """
    
    def __init__(self, config_path: Optional[str] = None, toml_path: Optional[str] = None):
        self.config_data = {}
        self._load_config(config_path, toml_path)
    
    def _load_config(self, config_path: Optional[str] = None, toml_path: Optional[str] = None):
        """
        Load configuration from multiple sources.
        Priority order:
        1. Environment variables
        2. TOML config file
        3. JSON config file
        4. Default values
        """
        # Load defaults
        self._load_defaults()
        
        # Load from JSON config file if provided
        if config_path:
            self._load_from_json(config_path)
        else:
            # Try to find JSON config file in standard locations
            standard_json_paths = [
                "config.json",
                os.path.join("config", "config.json"),
                os.path.join(os.path.dirname(__file__), "..", "config", "config.json")
            ]
            
            for path in standard_json_paths:
                if os.path.exists(path):
                    self._load_from_json(path)
                    break
        
        # Load from TOML config file if provided (higher priority than JSON)
        if toml_path:
            self._load_from_toml(toml_path)
        else:
            # Try to find TOML config file in standard locations
            standard_toml_paths = [
                "config.toml",
                os.path.join("config", "config.toml"),
                os.path.join(os.path.dirname(__file__), "..", "config", "config.toml")
            ]
            
            for path in standard_toml_paths:
                if os.path.exists(path):
                    self._load_from_toml(path)
                    break
        
        # Override with environment variables (highest priority)
        self._load_from_env()
        
        logger.info(f"Configuration loaded with {len(self.config_data)} settings")
    
    def _load_defaults(self):
        """Load default configuration values."""
        # Original default values...
        self.config_data = {
            # Rate limiting defaults
            "rate_limits.customer_per_minute": 10,
            "rate_limits.customer_per_hour": 50,
            "rate_limits.ip_per_minute": 20,
            "rate_limits.global_tps": 100,
            "rate_limits.enable_dynamic": True,
            
            # Fraud detection defaults
            "fraud.threshold": 0.7,
            "fraud.enable_ml_model": True,
            "fraud.ml_model_path": "models/fraud_model_v2.pkl",
            
            # Customer verification settings
            "customer.require_verification": True,
            "customer.verification_ttl_days": 30,
            
            # Performance settings
            "performance.cache_size": 10000,
            "performance.cache_ttl": 3600,
            
            # Logging settings
            "logging.level": "INFO",
            "logging.format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            
            # API settings with empty defaults for secrets
            "api.openai_api_key": ""
        }
    
    def _load_from_json(self, config_path: str):
        """Load configuration from a JSON file."""
        try:
            with open(config_path, 'r') as f:
                file_config = json.load(f)
            
            # Flatten nested structure
            self._update_with_nested_dict(file_config)
            logger.info(f"Loaded configuration from JSON: {config_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load JSON config from {config_path}: {str(e)}")
    
    def _load_from_toml(self, config_path: str):
        """Load configuration from a TOML file."""
        try:
            file_config = toml.load(config_path)
            
            # Flatten nested structure
            self._update_with_nested_dict(file_config)
            logger.info(f"Loaded configuration from TOML: {config_path}")
            
        except Exception as e:
            logger.warning(f"Failed to load TOML config from {config_path}: {str(e)}")
    
    def _load_from_env(self):
        """Load configuration from environment variables."""
        prefix = "TRANSACTION_"
        
        for key, value in os.environ.items():
            if key.startswith(prefix):
                # Convert environment variable name to config key
                config_key = key[len(prefix):].lower().replace("__", ".")
                
                # Try to parse as JSON for complex types
                try:
                    parsed_value = json.loads(value)
                    self.config_data[config_key] = parsed_value
                except json.JSONDecodeError:
                    # Use string value directly
                    self.config_data[config_key] = value
        
        # Specifically check for API keys that might have their own environment variables
        if 'OPENAI_API_KEY' in os.environ:
            self.config_data['api.openai_api_key'] = os.environ['OPENAI_API_KEY']
        
        logger.debug("Loaded configuration from environment variables")
    
    def _update_with_nested_dict(self, nested_dict: Dict[str, Any], prefix: str = ""):
        """
        Update configuration with a nested dictionary by flattening it.
        Example: {"rate_limits": {"customer_per_minute": 10}}
        Becomes: {"rate_limits.customer_per_minute": 10}
        """
        for key, value in nested_dict.items():
            flat_key = f"{prefix}{key}" if prefix else key
            
            if isinstance(value, dict):
                # Recurse into nested dictionaries
                self._update_with_nested_dict(value, f"{flat_key}.")
            else:
                # Store leaf values
                self.config_data[flat_key] = value
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: The configuration key
            default: Default value if key doesn't exist
            
        Returns:
            The configuration value or default
        """
        return self.config_data.get(key, default)
    
    def set(self, key: str, value: Any):
        """
        Set a configuration value at runtime.
        
        Args:
            key: The configuration key
            value: The value to set
        """
        self.config_data[key] = value
    
    def as_dict(self) -> Dict[str, Any]:
        """Get a copy of the entire configuration as a dictionary."""
        return self.config_data.copy()