import asyncio
import logging

from src.api.shared import connected_websockets

logger = logging.getLogger(__name__)

# Global Eco-Mode flag
ECO_MODE = False


def is_eco_mode_active() -> bool:
    """Return whether the machine is currently running on battery power (Eco-Mode)."""
    return ECO_MODE


def should_use_cloud_for_power() -> bool:
    """Check if Eco-Mode is active and cloud is configured to save battery power."""
    from src.config.secret_store import resolve_deepseek_api_key

    return bool(ECO_MODE and resolve_deepseek_api_key())


async def is_on_battery() -> bool:
    """Asynchronously check if Mac is running on battery using pmset."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "pmset",
            "-g",
            "batt",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if stdout:
            # 'pmset -g batt' outputs "Now drawing from 'Battery Power'" when unplugged
            return "Now drawing from 'Battery Power'" in stdout.decode()
        return False
    except asyncio.CancelledError:
        if "proc" in locals():
            try:
                proc.terminate()
            except Exception:
                pass
        raise
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
    ECO_MODE = await is_on_battery()

    while True:
        try:
            current_battery_state = await is_on_battery()
            if current_battery_state != ECO_MODE:
                logger.info("Power state changed. Eco-Mode: %s", current_battery_state)
                ECO_MODE = current_battery_state
                await broadcast_eco_mode(ECO_MODE)
        except Exception as e:
            logger.error("Error in power monitor loop: %s", e)

        await asyncio.sleep(60)
