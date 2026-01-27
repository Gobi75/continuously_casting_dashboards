"""Sensor platform for Continuously Casting Dashboards integration."""

import json
import logging
import os
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.components.sensor import SensorEntity, SensorEntityDescription, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, STATUS_FILE

_LOGGER = logging.getLogger(__name__)

EVENT_STATUS_UPDATED = f"{DOMAIN}_status_updated"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    _LOGGER.debug("Setting up sensor platform for entry %s", entry.entry_id)

    # Get the integration instance from hass.data
    if DOMAIN not in hass.data or entry.entry_id not in hass.data[DOMAIN]:
        _LOGGER.error("Integration data not found for entry %s", entry.entry_id)
        return

    integration_data = hass.data[DOMAIN][entry.entry_id]
    caster = integration_data.get("caster")
    config = integration_data.get("config", {})

    if not caster:
        _LOGGER.error("Caster instance not found for entry %s", entry.entry_id)
        return

    devices = config.get("devices", {})
    _LOGGER.debug("Found %d devices to create sensors for", len(devices))

    entities = []

    # Create global summary sensors
    entities.extend([
        ContinuouslyCastingSummarySensor(
            hass, entry, "total_devices", "Total Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "connected_devices", "Connected Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "disconnected_devices", "Disconnected Devices"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "media_playing_devices", "Media Playing"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "other_content_devices", "Other Content"
        ),
        ContinuouslyCastingSummarySensor(
            hass, entry, "assistant_active_devices", "Assistant Active"
        ),
    ])

    # Create a sensor for each device
    for device_name in devices.keys():
        entity = ContinuouslyCastingDeviceSensor(hass, entry, device_name)
        entities.append(entity)
        _LOGGER.debug("Created sensor for device: %s", device_name)

    if entities:
        async_add_entities(entities)
        _LOGGER.info("Added %d sensor entities", len(entities))

        # Listen for status updates to refresh sensors
        @callback
        def on_status_update(event):
            """Refresh all sensors when status is updated."""
            _LOGGER.debug("Received status update event, refreshing sensors")
            for entity in entities:
                hass.async_create_task(entity._async_refresh_and_write())

        # Register the event listener
        entry.async_on_unload(
            hass.bus.async_listen(EVENT_STATUS_UPDATED, on_status_update)
        )
        _LOGGER.debug("Registered status update event listener")
    else:
        _LOGGER.warning("No sensor entities to add")


def _read_status_data() -> dict:
    """Read status data from file (synchronous, run in executor)."""
    try:
        if not os.path.exists(STATUS_FILE):
            return {}

        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        _LOGGER.debug("Error reading status file: %s", e)
        return {}


class ContinuouslyCastingSensorBase(SensorEntity):
    """Base class for Continuously Casting Dashboards sensors."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Initialize the sensor base."""
        self.hass = hass
        self.entry = entry
        self._status_data = {}

    def _refresh_data(self):
        """Schedule a refresh of the status data without blocking."""
        async def _do_refresh():
            try:
                self._status_data = await self.hass.async_add_executor_job(_read_status_data)
            except Exception as e:
                _LOGGER.debug("Error refreshing status data: %s", e)

        self.hass.async_create_task(_do_refresh())

    async def async_added_to_hass(self) -> None:
        """Fetch initial data when entity is added."""
        await self._async_refresh_and_write()

    async def _async_refresh_and_write(self) -> None:
        """Refresh data in executor and write state."""
        try:
            self._status_data = await self.hass.async_add_executor_job(_read_status_data)
        except Exception as e:
            _LOGGER.debug("Error refreshing status data: %s", e)
        self.async_write_ha_state()

    async def async_update(self) -> None:
        """Update the sensor state."""
        await self._async_refresh_and_write()

    @property
    def device_info(self):
        """Return device information."""
        return {
            "identifiers": {(DOMAIN, self.entry.entry_id)},
            "name": "Continuously Casting Dashboards",
            "manufacturer": "Continuously Casting Dashboards",
            "model": "Integration",
        }

    @property
    def should_poll(self) -> bool:
        """Return False as we push updates."""
        return False


class ContinuouslyCastingSummarySensor(ContinuouslyCastingSensorBase):
    """Sensor for global summary statistics."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, sensor_type: str, friendly_name: str):
        """Initialize the summary sensor."""
        super().__init__(hass, entry)
        self._sensor_type = sensor_type
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{sensor_type}"
        self._attr_has_entity_name = True
        self._attr_name = friendly_name
        self._refresh_data()

    @property
    def native_value(self) -> int | None:
        """Return the state of the sensor."""
        return self._status_data.get(self._sensor_type)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        if not self._status_data:
            return None

        return {
            "last_updated": self._status_data.get("last_updated"),
        }


class ContinuouslyCastingDeviceSensor(ContinuouslyCastingSensorBase):
    """Sensor for individual device status."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, device_name: str):
        """Initialize the device sensor."""
        super().__init__(hass, entry)
        self._device_name = device_name
        self._attr_unique_id = f"{DOMAIN}_{entry.entry_id}_{device_name.replace(' ', '_').lower()}_status"
        self._attr_has_entity_name = True
        self._attr_name = f"{device_name} Status"
        self._refresh_data()

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        devices = self._status_data.get("devices", {})
        device_info = devices.get(self._device_name)
        if device_info:
            return device_info.get("status", "unknown")
        return "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return additional state attributes."""
        devices = self._status_data.get("devices", {})
        device_info = devices.get(self._device_name)
        if device_info:
            return {
                "ip": device_info.get("ip", "Unknown"),
                "last_checked": device_info.get("last_checked", ""),
                "reconnect_attempts": device_info.get("reconnect_attempts", 0),
                "device_name": self._device_name,
            }
        return None

    @property
    def entity_category(self) -> EntityCategory | None:
        """Return the entity category."""
        return EntityCategory.DIAGNOSTIC
