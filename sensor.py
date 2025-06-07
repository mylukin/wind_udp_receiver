from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfSpeed
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any, Optional, Union
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN, WIND_DIRECTION_MAP, WIND_LEVEL_MAP, BEAUFORT_SCALE_THRESHOLDS,
    DIRECTION_ANGLE_RANGES, WIND_SPEED_SCALE, WIND_DIRECTION_SCALE
)

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry, 
    async_add_entities: AddEntitiesCallback,
) -> None:
    """设置传感器实体"""
    
    try:
        sensors = [
            WindSpeedSensor(hass, entry.entry_id),           # 风速传感器
            WindLevelSensor(hass, entry.entry_id),           # 风级传感器
            WindDirectionSensor(hass, entry.entry_id),       # 风向角度传感器
            WindDirectionCodeSensor(hass, entry.entry_id),   # 风向编码传感器
            DeviceStatusSensor(hass, entry.entry_id),        # 设备状态传感器
            LastUpdateSensor(hass, entry.entry_id),          # 最后更新传感器
        ]
        
        async_add_entities(sensors, True)
        _LOGGER.info(f"已创建 {len(sensors)} 个风力传感器实体")
        
    except Exception as e:
        _LOGGER.error(f"设置传感器实体失败: {e}")

class BaseWindSensor(SensorEntity):
    """风力传感器基类"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str, sensor_type: str, 
                 name: str, unique_id: str, icon: str = "mdi:weather-windy"):
        self.hass = hass
        self.entry_id = entry_id
        self.sensor_type = sensor_type
        self._attr_name = name
        self._attr_unique_id = f"{DOMAIN}_{unique_id}_{entry_id}"
        self._attr_icon = icon
        self._attr_native_value = None
        self._attr_should_poll = False
        
    async def async_added_to_hass(self) -> None:
        """当传感器添加到HA时注册事件监听"""
        await super().async_added_to_hass()
        
        @callback
        def handle_wind_event(event):
            """处理风力事件"""
            try:
                if not self.entity_id:
                    _LOGGER.debug(f"{self.sensor_type}传感器实体ID尚未设置，跳过更新")
                    return
                
                event_type = event.data.get('event_type')
                if event_type == 'wind_data_received':
                    self._handle_wind_data(event.data.get('wind_data', {}))
                    
            except Exception as e:
                _LOGGER.error(f"{self.sensor_type}传感器事件处理失败: {e}")
        
        # 注册事件监听
        self.async_on_remove(
            self.hass.bus.async_listen(f'{DOMAIN}_event', handle_wind_event)
        )
    
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理风力数据 - 子类需要重写此方法"""
        raise NotImplementedError("子类必须实现 _handle_wind_data 方法")
    
    def _update_state(self, value: Union[int, float, str], log_message: str = "") -> None:
        """更新传感器状态"""
        self._attr_native_value = value
        self.async_write_ha_state()
        
        if log_message:
            _LOGGER.info(f"{self.sensor_type}: {log_message}")

class WindSpeedSensor(BaseWindSensor):
    """风速传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        super().__init__(
            hass, entry_id, "风速", "Wind Speed", "wind_speed", "mdi:weather-windy"
        )
        self._attr_native_unit_of_measurement = UnitOfSpeed.METERS_PER_SECOND
        self._attr_device_class = SensorDeviceClass.WIND_SPEED
        
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理风速数据"""
        if '0' in wind_data:
            raw_value = wind_data['0']
            wind_speed_ms = raw_value / WIND_SPEED_SCALE  # 转换为m/s
            
            self._update_state(
                wind_speed_ms, 
                f"风速更新为 {wind_speed_ms:.1f} m/s (原始值: {raw_value})"
            )
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回额外状态属性"""
        if self._attr_native_value is not None:
            return {
                "wind_speed_ms": self._attr_native_value,
                "wind_speed_kmh": round(self._attr_native_value * 3.6, 2),
                "beaufort_scale": self._get_beaufort_scale(self._attr_native_value),
                "raw_value": int(self._attr_native_value * 10),
                "description": "风速 (m/s)"
            }
        return {}
    
    def _get_beaufort_scale(self, speed_ms: float) -> str:
        """根据风速计算蒲福风级"""
        for threshold, description in BEAUFORT_SCALE_THRESHOLDS:
            if speed_ms < threshold:
                return description
        return "12级 (飓风)"

class WindLevelSensor(BaseWindSensor):
    """风级传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        super().__init__(
            hass, entry_id, "风级", "Wind Level", "wind_level", "mdi:windsock"
        )
        self._attr_native_unit_of_measurement = "级"
        
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理风级数据"""
        if '1' in wind_data:
            wind_level = wind_data['1']
            
            self._update_state(
                wind_level, 
                f"风级更新为 {wind_level}级"
            )
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回额外状态属性"""
        if self._attr_native_value is not None:
            return {
                "wind_level": self._attr_native_value,
                "level_description": WIND_LEVEL_MAP.get(self._attr_native_value, f"{self._attr_native_value}级"),
                "description": "风力等级"
            }
        return {}

class WindDirectionSensor(BaseWindSensor):
    """风向角度传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        super().__init__(
            hass, entry_id, "风向角度", "Wind Direction Angle", "wind_direction_angle", "mdi:compass"
        )
        self._attr_native_unit_of_measurement = "°"
        
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理风向角度数据"""
        if '2' in wind_data:
            raw_value = wind_data['2']
            wind_direction_deg = raw_value / WIND_DIRECTION_SCALE  # 转换为度数
            
            self._update_state(
                wind_direction_deg, 
                f"风向角度更新为 {wind_direction_deg:.1f}° (原始值: {raw_value})"
            )
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回额外状态属性"""
        if self._attr_native_value is not None:
            return {
                "angle_degrees": self._attr_native_value,
                "cardinal_direction": self._get_cardinal_direction(self._attr_native_value),
                "raw_value": int(self._attr_native_value * 10),
                "description": "风向角度 (0°=北, 90°=东, 180°=南, 270°=西)"
            }
        return {}
    
    def _get_cardinal_direction(self, angle: float) -> str:
        """根据角度获取方位名称"""
        angle = angle % 360  # 标准化角度到0-360范围
        
        for threshold, direction in DIRECTION_ANGLE_RANGES:
            if angle < threshold:
                return direction
        return "北"  # 348.75°以上回到北

class WindDirectionCodeSensor(BaseWindSensor):
    """风向编码传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        super().__init__(
            hass, entry_id, "风向编码", "Wind Direction Code", "wind_direction_code", "mdi:compass-rose"
        )
        
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理风向编码数据"""
        if '3' in wind_data:
            wind_direction_code = wind_data['3']
            direction_name = WIND_DIRECTION_MAP.get(wind_direction_code, f"未知编码(0x{wind_direction_code:02X})")
            
            self._update_state(
                direction_name, 
                f"风向编码更新为 0x{wind_direction_code:02X} -> {direction_name}"
            )
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回额外状态属性"""
        if self._attr_native_value:
            # 从风向名称反推编码
            code = None
            for code_val, name in WIND_DIRECTION_MAP.items():
                if name == str(self._attr_native_value):
                    code = code_val
                    break
            
            return {
                "direction_name": self._attr_native_value,
                "raw_code_hex": f"0x{code:02X}" if code is not None else "未知",
                "raw_code_dec": code if code is not None else "未知",
                "description": "16方位风向编码"
            }
        return {}

class DeviceStatusSensor(SensorEntity):
    """设备状态传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        self.hass = hass
        self.entry_id = entry_id
        self._attr_name = "Device Status"
        self._attr_unique_id = f"{DOMAIN}_device_status_{entry_id}"
        self._attr_native_value = "等待连接"
        self._attr_should_poll = True
        self._attr_icon = "mdi:connection"
        self._last_activity = None
        self._offline_threshold = 10  # 离线阈值（秒）
        
    async def async_added_to_hass(self) -> None:
        """注册事件监听"""
        @callback
        def update_activity(event):
            """更新设备活跃时间"""
            try:
                self._last_activity = asyncio.get_event_loop().time()
                self._update_status_immediate()
                
            except Exception as e:
                _LOGGER.error(f"设备状态更新失败: {e}")
        
        # 监听所有wind_udp_receiver_event事件
        self.async_on_remove(
            self.hass.bus.async_listen(f'{DOMAIN}_event', update_activity)
        )
        
    def _update_status_immediate(self) -> None:
        """立即更新状态为在线"""
        self._attr_native_value = "在线"
        self._attr_icon = "mdi:check-network"
        self.async_write_ha_state()
        _LOGGER.debug("设备状态更新为: 在线")
        
    async def async_update(self) -> None:
        """定期检查离线状态"""
        self._update_status()
        
    def _update_status(self) -> None:
        """更新设备状态"""
        try:
            if self._last_activity is None:
                self._attr_native_value = "等待连接"
                self._attr_icon = "mdi:connection"
            else:
                current_time = asyncio.get_event_loop().time()
                offline_duration = current_time - self._last_activity
                
                if offline_duration < self._offline_threshold:
                    self._attr_native_value = "在线"
                    self._attr_icon = "mdi:check-network"
                else:
                    minutes_offline = int(offline_duration // 60)
                    self._attr_native_value = f"离线 {minutes_offline}分钟"
                    self._attr_icon = "mdi:network-off"
            
            self.async_write_ha_state()
        except Exception as e:
            _LOGGER.error(f"状态更新失败: {e}")
        
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """返回额外状态属性"""
        try:
            if self._last_activity is None:
                return {
                    "last_activity": None,
                    "offline_threshold_minutes": self._offline_threshold // 60,
                    "status": "等待连接"
                }
            
            current_time = asyncio.get_event_loop().time()
            offline_duration = current_time - self._last_activity
            last_activity_dt = dt_util.utc_from_timestamp(self._last_activity).astimezone(dt_util.DEFAULT_TIME_ZONE)
            
            return {
                "last_activity": last_activity_dt.strftime("%Y-%m-%d %H:%M:%S"),
                "offline_duration_seconds": int(offline_duration),
                "offline_threshold_minutes": self._offline_threshold // 60,
                "is_online": offline_duration < self._offline_threshold,
                "status": "在线" if offline_duration < self._offline_threshold else "离线"
            }
        except Exception as e:
            _LOGGER.error(f"获取状态属性失败: {e}")
            return {}

class LastUpdateSensor(BaseWindSensor):
    """最后更新时间传感器"""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        super().__init__(
            hass, entry_id, "最后更新", "Last Update", "last_update", "mdi:clock-outline"
        )
        self._attr_native_value = "从未更新"
        # 禁用历史记录
        self._attr_state_class = None
        self._attr_force_update = True
        
    def _handle_wind_data(self, wind_data: Dict[str, Any]) -> None:
        """处理更新时间"""
        # 使用Home Assistant的时区感知时间
        current_time = dt_util.now().strftime("%Y-%m-%d %H:%M:%S")
        self._update_state(current_time, f"数据更新时间: {current_time}")

