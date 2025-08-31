from src.core.config import get_config
cfg = get_config()
print("dotenv_count", len(cfg._dotenv))
print("dotenv_has_key", DATABENTO_API_KEY in cfg._dotenv)
print("dotenv_val_head", (cfg._dotenv.get(DATABENTO_API_KEY) or )[:8])
print("get_env_head", (cfg.get_env(DATABENTO_API_KEY) or )[:8])
print("databento_api_key_head", (cfg.databento_api_key() or )[:8])
