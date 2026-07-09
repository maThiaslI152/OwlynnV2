import asyncio
import subprocess
import logging
from src.api.shared import connected_websockets

logger = logging.getLogger(__name__)

# Global Eco-Mode flag
ECO_MODE = False


def is_on_battery() -> bool:
    """Synchronously check if Mac is running on battery using pmset."""
    try:
        result = subprocess.run(
            ["pmset", "-g", "batt"], capture_output=True, text=True, check=True
        )
        # 'pmset -g batt' outputs "Now drawing from 'Battery Power'" when unplugged
        return "Now drawing from 'Battery Power'" in result.stdout
    except Exception as e:
        logger.warning("Failed to check battery status: %s", e)
        return False


async def broadcast_eco_mode(is_eco: bool):
    """Broadcast the eco mode state to all connected WebSockets."""
    from src.api.server import app

    loop = getattr(app.state, "loop", None) or asyncio.get_running_loop()

    payload = {"type": "eco_mode_changed", "isEcoMode": is_eco}

    for ws in list(connected_websockets):
        try:
            coro = ws.send_json(payload)
            asyncio.run_coroutine_threadsafe(coro, loop)
        except Exception as e:
            logger.warning("Failed to send eco_mode_changed to websocket: %s", e)


async def power_monitor_loop():
    """Background task to poll battery status every 60 seconds."""
    global ECO_MODE
    logger.info("Power monitor loop started.")

    # Initialize state
    ECO_MODE = is_on_battery()

    while True:
        try:
            current_battery_state = is_on_battery()
            if current_battery_state != ECO_MODE:
                logger.info("Power state changed. Eco-Mode: %s", current_battery_state)
                ECO_MODE = current_battery_state
                await broadcast_eco_mode(ECO_MODE)
        except Exception as e:
            logger.error("Error in power monitor loop: %s", e)

        await asyncio.sleep(60)
