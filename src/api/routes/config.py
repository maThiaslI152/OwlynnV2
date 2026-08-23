import yaml
from fastapi import APIRouter

from src.config.config_loader import _DEFAULTS_PATH, config

router = APIRouter()


@router.get("/api/config")
async def get_config():
    return config.get_config()


@router.post("/api/config")
async def update_config(body: dict):
    try:
        with open(_DEFAULTS_PATH, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        data = {}

    def deep_update(d, u):
        for k, v in u.items():
            if isinstance(v, dict):
                d[k] = deep_update(d.get(k, {}), v)
            else:
                d[k] = v
        return d

    deep_update(data, body)

    with open(_DEFAULTS_PATH, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False)

    config.reload()
    return {"status": "success"}
