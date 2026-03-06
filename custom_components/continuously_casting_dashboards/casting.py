"""Casting functionality - precise volume and clean logging."""
import asyncio
import logging
import time
import re
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

class CastingManager:
    def __init__(self, hass: HomeAssistant, config: dict, device_manager):
        self.hass = hass
        self.config = config
        self.device_manager = device_manager
        self.active_casting_operations = {}

    async def _get_raw_info(self, ip):
        try:
            process = await asyncio.create_subprocess_exec('catt', '-d', ip, 'info', stdout=asyncio.subprocess.PIPE)
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=10)
            return stdout.decode().strip()
        except: return ""

    async def async_cast_dashboard(self, ip, dashboard_url, device_config):
        if ip in self.active_casting_operations: return False
        self.active_casting_operations[ip] = {'start_time': time.time()}
        try:
            # 1. Pobieranie głośności - Logika poprawiona o priorytet checkboxa
            if device_config.get("override_volume", False):
                vol_to_set = int(device_config.get("volume", 5))
                log_msg = f"Wymuszono głośność z ustawień: {vol_to_set}%"
            else:
                info = await self._get_raw_info(ip)
                match = re.search(r'volume_level:\s*([\d\.]+)', info)
                vol_raw = match.group(1) if match else "0.1"
                vol_to_set = int(round(float(vol_raw) * 100))
                log_msg = f"Zapamiętano głośność: {vol_to_set}%"

            _LOGGER.info(f"CAST START: {ip} | {log_msg}")

            # 2. Procedura rzutowania
            await (await asyncio.create_subprocess_exec('catt', '-d', ip, 'volume', '0')).wait()
            await (await asyncio.create_subprocess_exec('catt', '-d', ip, 'stop')).wait()
            await (await asyncio.create_subprocess_exec('catt', '-d', ip, 'cast_site', dashboard_url)).wait()

            # 3. Stabilizacja
            await asyncio.sleep(15)
            
            # 4. Ustawienie docelowej głośności
            await (await asyncio.create_subprocess_exec('catt', '-d', ip, 'volume', str(vol_to_set))).wait()
            _LOGGER.info(f"CAST SUCCESS: {ip} | Dashboard aktywny, głośność: {vol_to_set}%")

            return True
        except Exception as e:
            _LOGGER.error(f"CAST ERROR on {ip}: {e}")
            return False
        finally:
            self.active_casting_operations.pop(ip, None)

    async def async_get_current_volume(self, ip): 
        return 5