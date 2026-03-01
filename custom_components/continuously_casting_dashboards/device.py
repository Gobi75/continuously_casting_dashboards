"""Device discovery and management for Continuously Casting Dashboards."""
import asyncio
import logging
import time
import re
from datetime import datetime
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

# Simple IPv4 validation regex
IP_PATTERN = re.compile(r'^(\d{1,3}\.){3}\d{1,3}$')

class DeviceManager:
    """Class to manage device discovery and status checks."""

    def __init__(self, hass: HomeAssistant, config: dict):
        """Initialize the device manager."""
        self.hass = hass
        self.config = config
        self.device_ip_cache = {}  # Cache for device IPs
        self.active_devices = {}   # Track active devices
        self.active_checks = {}    # Track active status checks
        self.status_cache = {}     # Short-lived cache for catt status output

    def _cache_status_output(self, ip, output):
        """Cache status output briefly to avoid duplicate catt calls."""
        if not output:
            return
        self.status_cache[ip] = {
            "output": output,
            "timestamp": time.time(),
        }

    def _get_cached_status_output(self, ip, max_age=2.0):
        """Get cached status output if it's fresh enough."""
        cached = self.status_cache.get(ip)
        if not cached:
            return None
        if (time.time() - cached.get("timestamp", 0)) > max_age:
            return None
        return cached.get("output")

    def _status_indicates_assistant_activity(self, status_output):
        """Detect Google Assistant/timer activity from catt status output."""
        if not status_output:
            return False
        status_lower = status_output.lower()
        sanitized = status_lower.replace("homeassistant", "").replace("home assistant", "")

        if "google assistant" in sanitized:
            return True
        if re.search(r"\bassistant\b", sanitized):
            return True

        assistant_keywords = ["timer", "alarm", "reminder", "stopwatch", "countdown"]
        return any(keyword in sanitized for keyword in assistant_keywords)

    async def _async_run_status_command(self, ip, timeout=15):
        """Run status command and show full output ONLY in DEBUG mode."""
        cmd = ['catt', '-d', ip, 'info']
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout)
            output = stdout.decode().strip()
            
            # PEŁNY STATUS TYLKO DLA DEBUG
            if output:
                _LOGGER.debug(f"--- FULL DEVICE STATUS [{ip}] ---\n{output}\n---------------------------")
            
            return output, stderr.decode(), process.returncode, None
        except Exception as e:
            return None, None, None, str(e)

    async def _async_execute_device_command(self, ip, command_str, timeout=10.0):
        """Execute a control command (like volume 0, stop, etc.) via catt."""
        cmd_parts = command_str.split()
        cmd = ['catt', '-d', ip] + cmd_parts
        _LOGGER.debug(f"EXECUTING CONTROL COMMAND: {' '.join(cmd)}")
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            await asyncio.wait_for(process.communicate(), timeout=timeout)
            return process.returncode == 0
        except Exception as e:
            _LOGGER.error(f"Failed to execute '{command_str}' on {ip}: {str(e)}")
            return False

    async def async_get_device_ip(self, device_name_or_ip):
        """Get IP address for a device name or directly use IP."""
        if IP_PATTERN.match(device_name_or_ip):
            return device_name_or_ip
        
        try:
            process = await asyncio.create_subprocess_exec(
                'catt', 'scan', stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=15.0)
            for line in stdout.decode().splitlines():
                if ' - ' in line:
                    parts = line.split(' - ')
                    ip, found_name = parts[0].strip(), parts[1].strip()
                    if found_name.lower() == device_name_or_ip.lower():
                        return ip
            return None
        except:
            return None

    async def async_is_media_playing(self, ip):
        """Check if media is playing or paused on the device."""
        stdout_str, _, returncode, _ = await self._async_run_status_command(ip)
        if not stdout_str or returncode != 0:
            return False

        status_lower = stdout_str.lower()
        if "84912283" in stdout_str: return True # DashCast
        if "e8c28d3c" in status_lower or "backdrop" in status_lower: return False

        media_apps = ["spotify", "youtube", "netflix", "plex", "disney+", "hulu"]
        if any(app in status_lower for app in media_apps): return True
        
        return any(x in stdout_str for x in ["PLAYING", "PAUSED", "BUFFERING"])

    async def async_is_assistant_active(self, ip, status_output=None):
        """Check if Google Assistant is active."""
        if status_output is None:
            status_output = self._get_cached_status_output(ip)
        if status_output is None:
            status_output, _, _, _ = await self._async_run_status_command(ip)
        return self._status_indicates_assistant_activity(status_output)

    async def async_check_device_status(self, ip):
        """Check if a device is still casting our dashboard."""
        stdout_str, _, returncode, _ = await self._async_run_status_command(ip)
        if stdout_str and returncode == 0:
            return any(x in stdout_str.lower() for x in ["84912283", "dashcast", "dummy"])
        return False

    async def async_check_speaker_group_state(self, ip, speaker_groups):
        """Check if any of the speaker groups is active."""
        if not speaker_groups: return False
        for group in speaker_groups:
            try:
                cmd = ['catt', '-d', group, 'info']
                p = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE)
                out, _ = await asyncio.wait_for(p.communicate(), timeout=5.0)
                if "PLAYING" in out.decode(): return True
            except: continue
        return False

    def get_active_device(self, device_key):
        return self.active_devices.get(device_key)

    def update_active_device(self, device_key, status, **kwargs):
        if device_key in self.active_devices:
            self.active_devices[device_key].update(status=status, **kwargs)
        else:
            self.active_devices[device_key] = {'status': status, **kwargs}

    def get_all_active_devices(self):
        return self.active_devices

    def get_device_current_dashboard(self, device_key):
        return self.active_devices.get(device_key, {}).get('current_dashboard')