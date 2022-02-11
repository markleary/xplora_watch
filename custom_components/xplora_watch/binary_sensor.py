"""Reads Xplora® Watch status."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription
)
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    ATTR_WATCH,
    BINARY_SENSOR_CHARGING,
    BINARY_SENSOR_SAFEZONE,
    BINARY_SENSOR_STATE,
    CONF_CHILD_PHONENUMBER,
    CONF_TYPES,
    DATA_XPLORA,
    XPLORA_CONTROLLER
)
from .helper import XploraUpdateTime
from pyxplora_api import pyxplora_api_async as PXA

_LOGGER = logging.getLogger(__name__)

BINARY_SENSOR_TYPES: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key=BINARY_SENSOR_CHARGING,
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
    ),
    BinarySensorEntityDescription(
        key=BINARY_SENSOR_SAFEZONE,
        device_class=BinarySensorDeviceClass.SAFETY,
    ),
    BinarySensorEntityDescription(
        key=BINARY_SENSOR_STATE,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)

async def async_setup_platform(
    hass: HomeAssistant,
    conf: ConfigType,
    add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None
) -> None:
    if discovery_info is None:
        return
    controller: PXA.PyXploraApi = hass.data[DATA_XPLORA][discovery_info[XPLORA_CONTROLLER]]
    child_no = hass.data[CONF_CHILD_PHONENUMBER][discovery_info[XPLORA_CONTROLLER]]
    scan_interval = hass.data[CONF_SCAN_INTERVAL][discovery_info[XPLORA_CONTROLLER]]
    start_time = datetime.timestamp(datetime.now())
    _types = hass.data[CONF_TYPES][discovery_info[XPLORA_CONTROLLER]]

    for description in BINARY_SENSOR_TYPES:
        if description.key in _types:
            add_entities([
                XploraBinarySensor(
                    description,
                    controller,
                    scan_interval,
                    start_time,
                    _types,
                    child_no)
                ], True)

class XploraBinarySensor(BinarySensorEntity, XploraUpdateTime):

    def __init__(
        self,
        description: BinarySensorEntity,
        controller: PXA.XploraApi,
        scan_interval,
        start_time,
        _types: str,
        child_no
    ) -> None:
        super().__init__(scan_interval, start_time)
        self.entity_description = description
        self._controller: PXA.PyXploraApi = controller
        self._types = _types
        self._child_no = child_no
        _LOGGER.debug(f"set Binary Sensor: {self.entity_description.key}")

    async def __isOnline(self, id) -> bool:
        await self._controller.init_async()
        self._attr_icon = "mdi:lan-check"
        if (await self._controller.askWatchLocate_async(id) == True) or (await self._controller.trackWatchInterval_async(id) != -1):
            return True
        state = await self._controller.getWatchOnlineStatus_async(id)
        if (state == "ONLINE"):
            return True
        self._attr_icon = "mdi:lan-disconnect"
        return False

    async def __isSafezone(self, id) -> bool:
        if await self._controller.getWatchIsInSafeZone_async(id):
            return False
        return True

    async def __isCharging(self, id) -> bool:
        if await self._controller.getWatchIsCharging_async(id):
            return True
        return False

    async def __isTypes(self, sensor_type: str) -> bool:
        if sensor_type in self._types and self.entity_description.key == sensor_type:
            return True
        return False

    async def __default_attr(self, fun, sensor_type, id) -> None:
        self._attr_native_value = fun
        client_name = await self._controller.getWatchUserName_async(id)
        self._attr_name = f"{client_name} {ATTR_WATCH} {sensor_type} {id}".title()
        self._attr_unique_id = f"{id}{self._attr_name}"
        self._attr_is_on = fun

    async def __update(self, id) -> None:
        if await self.__isTypes(BINARY_SENSOR_STATE):
            await self.__default_attr((await self.__isOnline(id)), BINARY_SENSOR_STATE, id)

            _LOGGER.debug("Updating sensor: %s | State: %s", self._attr_name, str(self._attr_is_on))

        elif await self.__isTypes(BINARY_SENSOR_SAFEZONE):
            await self.__default_attr((await self.__isSafezone(id)), BINARY_SENSOR_SAFEZONE, id)

            _LOGGER.debug("Updating sensor: %s | State: %s", self._attr_name, str(self._attr_is_on))

        elif await self.__isTypes(BINARY_SENSOR_CHARGING):
            await self.__default_attr((await self.__isCharging(id)), BINARY_SENSOR_CHARGING, id)

            _LOGGER.debug("Updating sensor: %s | State: %s", self._attr_name, str(self._attr_is_on))

    async def async_update(self) -> None:
        if self._update_timer() or self._first:
            self._first = False
            self._start_time = datetime.timestamp(datetime.now())
            for id in self._child_no:
                await self.__update(id)
