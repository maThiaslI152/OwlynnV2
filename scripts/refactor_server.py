import os

def refactor_server():
    server_path = "src/api/server.py"
    with open(server_path, 'r') as f:
        lines = f.readlines()
    
    # We will define the blocks to extract.
    # Format: filename, start_line, end_line, custom_header
    blocks = [
        (
            "src/api/routes/profile.py",
            355, 401,
            """from fastapi import APIRouter, Request, Response, HTTPException
import json
from src.memory.user_profile import get_profile, update_profile, VALID_FIELDS
from src.memory.persona import get_persona, update_persona_field
from src.config.audit_log import audit_info, audit_debug
from pydantic import BaseModel
from typing import Dict, Any

router = APIRouter()

"""
        ),
        (
            "src/api/routes/settings.py",
            410, 555, # up to before health
            """from fastapi import APIRouter, Request, Response, HTTPException
import json
from src.memory.user_profile import get_profile, update_profile
from src.config.audit_log import audit_info, audit_debug
from typing import Dict, Any

router = APIRouter()

"""
        ),
        (
            "src/api/routes/memory.py",
            632, 753, # up to before topics
            """from fastapi import APIRouter, Request, Response, HTTPException
import json
import logging
from src.memory.memory_manager import load_memories, save_memory, delete_memory
from src.memory.long_term import memory as mem0_memory
from src.config.audit_log import audit_info, audit_debug
from typing import Dict, Any

logger = logging.getLogger(__name__)
router = APIRouter()

"""
        ),
    ]

    # Add settings continuation (621-631)
    # Actually wait, /api/advanced-settings is at 621. Let's merge it into settings.py.
    # It's easier to just use Python to find the functions by name or @app.xxx
    pass

refactor_server()
