import json, os

CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.json")

def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {}

def save_config(data: dict):
    with open(CONFIG_PATH, "w") as f:
        json.dump(data, f, indent=2)

def is_first_run() -> bool:
    config = load_config()
    return not (config.get("agent_id") and config.get("token"))

def write_pending_registration(activation_code: str, server_url: str):
    """Write a pending registration file that ensure_registered will pick up."""
    # Use update to preserve existing settings like server_url if needed
    config = load_config()
    config.update({
        "pending_activation_code": activation_code, 
        "server_url": server_url
    })
    save_config(config)
