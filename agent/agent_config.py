import json
import os
import platform
import subprocess
import logging

_OS = platform.system()
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_config.json")
logger = logging.getLogger("AgentConfig")


def restrict_config_permissions():
    """Lock agent_config.json to owner-only read/write (600 on Unix, icacls on Windows)."""
    if not os.path.exists(CONFIG_PATH):
        return
    try:
        if _OS == "Windows":
            username = os.environ.get("USERNAME", "")
            if username:
                # Remove inherited permissions, grant current user Full Control only
                subprocess.run(
                    ["icacls", CONFIG_PATH, "/inheritance:r",
                     "/grant:r", f"{username}:(R,W)"],
                    check=True, capture_output=True
                )
        else:
            os.chmod(CONFIG_PATH, 0o600)
    except Exception as e:
        logger.warning(f"[CONFIG] Could not restrict permissions on config file: {e}")


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[CONFIG] Failed to read config: {e}")
    return {}


def save_config(data: dict):
    try:
        with open(CONFIG_PATH, "w") as f:
            json.dump(data, f, indent=2)
        restrict_config_permissions()
    except Exception as e:
        logger.error(f"[CONFIG] Failed to save config: {e}")
        raise


def is_first_run() -> bool:
    config = load_config()
    return not (config.get("agent_id") and config.get("token"))


def write_pending_registration(activation_code: str, server_url: str, tls_verify: bool = True):
    """Write activation code and server URL; preserves any existing settings."""
    config = load_config()
    config.update({
        "pending_activation_code": activation_code,
        "server_url": server_url,
        "tls_verify": tls_verify,
    })
    save_config(config)


def clear_credentials():
    """Remove all credentials so the agent can be re-registered."""
    config = load_config()
    for key in ("agent_id", "token", "location_id", "pending_activation_code"):
        config.pop(key, None)
    save_config(config)
    logger.info("[CONFIG] Credentials cleared — re-run agent_setup.py to register again")
