import json
import os
from typing import Dict, Any, Optional
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class ConfigManager:
    """Manages agent configuration with support for dynamic updates"""
    
    def __init__(self, config_path: str = "agent_config.json"):
        self.config_path = Path(config_path)
        self.config: Dict[str, Any] = {}
        self.load_config()
    
    def load_config(self) -> None:
        """Load configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    self.config = json.load(f)
                logger.info(f"Configuration loaded from {self.config_path}")
            else:
                self.config = self.get_default_config()
                self.save_config()
                logger.info("Default configuration created")
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self.config = self.get_default_config()
    
    def save_config(self) -> None:
        """Save current configuration to file"""
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=2)
            logger.info(f"Configuration saved to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")
    
    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration"""
        return {
            "agent_settings": {
                "system_prompt": """You are Rachel, a charismatic Irish professional human real estate agent working at Continental Real Estate in the UAE...""",
                "welcome_message": "Welcome to Continental Real Estate. Rachel here. How can I help?",
                "llm_choice": "groq",
                "stt_choice": "groq", 
                "tts_choice": "elevenlabs"
            },
            "llm_configs": {
                "groq": {
                    "model": "meta-llama/llama-4-maverick-17b-128e-instruct",
                    "temperature": 0.4
                },
                "openai": {
                    "model": "gpt-4o",
                    "temperature": 0.3
                }
            },
            "stt_configs": {
                "groq": {
                    "model": "whisper-large-v3-turbo",
                    "language": "en"
                },
                "deepgram": {
                    "model": "nova-2",
                    "language": "en-US"
                }
            },
            "tts_configs": {
                "elevenlabs": {
                    "model": "eleven_flash_v2_5",
                    "voice_id": "h8eW5xfRUGVJrZhAFxqK",
                    "voice_name": "Isla"
                },
                "openai": {
                    "model": "gpt-4o-mini-tts",
                    "voice": "shimmer"
                }
            },
            "telephony": {
                "phone_number": "",
                "sip_trunk_uri": "",
                "username": "",
                "password": ""
            },
            "integrations": {
                "google_sheets": {
                    "enabled": True,
                    "sheet_id": "",
                    "credentials_file": "google_credentials.json"
                },
                "pinecone": {
                    "enabled": True,
                    "index": "continental-property-data",
                    "namespace": "continental-property-data"
                }
            },
            "logging": {
                "level": "INFO",
                "file": "voice-agent.log"
            }
        }
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by dot notation (e.g., 'agent_settings.llm_choice')"""
        keys = key.split('.')
        value = self.config
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        return value
    
    def set(self, key: str, value: Any) -> None:
        """Set configuration value by dot notation"""
        keys = key.split('.')
        config = self.config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value
    
    def update_config(self, updates: Dict[str, Any]) -> None:
        """Update multiple configuration values"""
        def deep_update(d, u):
            for k, v in u.items():
                if isinstance(v, dict):
                    d[k] = deep_update(d.get(k, {}), v)
                else:
                    d[k] = v
            return d
        
        deep_update(self.config, updates)
        self.save_config()
    
    def validate_config(self) -> Dict[str, bool]:
        """Validate current configuration"""
        validation_results = {
            "api_keys": True,
            "telephony": True,
            "integrations": True
        }
        
        # Check API keys
        required_api_keys = []
        llm_choice = self.get("agent_settings.llm_choice")
        stt_choice = self.get("agent_settings.stt_choice")
        tts_choice = self.get("agent_settings.tts_choice")
        
        if llm_choice == "groq":
            required_api_keys.append("GROQ_API_KEY")
        elif llm_choice == "openai":
            required_api_keys.append("OPENAI_API_KEY")
            
        if stt_choice == "groq":
            required_api_keys.append("GROQ_API_KEY")
        elif stt_choice == "deepgram":
            required_api_keys.append("DEEPGRAM_API_KEY")
            
        if tts_choice == "elevenlabs":
            required_api_keys.append("ELEVENLABS_API_KEY")
        elif tts_choice == "openai":
            required_api_keys.append("OPENAI_API_KEY")
        
        for key in required_api_keys:
            if not os.getenv(key):
                validation_results["api_keys"] = False
                break
        
        # Check telephony configuration
        phone_number = self.get("telephony.phone_number")
        if not phone_number:
            validation_results["telephony"] = False
        
        return validation_results