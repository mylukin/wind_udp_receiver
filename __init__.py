import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, PLATFORMS, MODBUS_DEVICE_ADDR, MODBUS_FUNCTION_CODE, 
    MODBUS_DATA_LENGTH, MODBUS_EXPECTED_LENGTH, OFFLINE_THRESHOLD, 
    HEARTBEAT_INDICATORS, REGISTRATION_INDICATORS, WIND_SPEED_SCALE, 
    WIND_DIRECTION_SCALE
)

_LOGGER = logging.getLogger(__name__)

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (deprecated)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    _LOGGER.info("正在设置 Wind UDP Receiver 集成")
    
    try:
        # 启动UDP服务器
        port = entry.data.get("port", 8888)
        udp_server = UDPWindServer(hass, port)
        await udp_server.start()
        
        # 保存服务器实例
        hass.data.setdefault(DOMAIN, {})
        hass.data[DOMAIN][entry.entry_id] = {"server": udp_server}
        
        # 注册服务
        await _register_services(hass, udp_server)
        
        # 设置传感器平台
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        _LOGGER.info(f"Wind UDP Receiver 设置完成，端口: {port}")
        return True
        
    except Exception as e:
        _LOGGER.error(f"设置 Wind UDP Receiver 失败: {e}")
        return False

async def _register_services(hass: HomeAssistant, udp_server: 'UDPWindServer') -> None:
    """注册Home Assistant服务"""
    async def get_device_status(call):
        """获取设备状态服务"""
        try:
            status = udp_server.get_client_status()
            _LOGGER.debug(f"设备状态查询结果: {len(status)} 个设备")
            
            message = _format_device_status_message(status)
            
            await hass.services.async_call(
                'persistent_notification', 'create',
                {'message': message, 'title': 'Wind UDP Receiver 设备状态'}
            )
        except Exception as e:
            _LOGGER.error(f"获取设备状态失败: {e}")
    
    hass.services.async_register(DOMAIN, "get_device_status", get_device_status)

def _format_device_status_message(status: Dict[str, Any]) -> str:
    """格式化设备状态消息"""
    if not status:
        return "设备状态:\n暂无设备连接"
    
    message = "设备状态:\n"
    for addr, info in status.items():
        online_status = "在线" if info['online'] else f"离线({info['offline_duration']:.0f}秒)"
        device_type = info.get('type', '未知')
        message += f"设备 {addr}: {online_status} ({device_type})\n"
    
    return message

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目"""
    try:
        server_data = hass.data[DOMAIN].pop(entry.entry_id)
        await server_data["server"].stop()
        
        hass.services.async_remove(DOMAIN, "get_device_status")
        
        result = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        _LOGGER.info("Wind UDP Receiver 已成功卸载")
        return result
        
    except Exception as e:
        _LOGGER.error(f"卸载 Wind UDP Receiver 失败: {e}")
        return False

class UDPWindServer:
    """UDP风力传感器服务器"""
    
    def __init__(self, hass: HomeAssistant, port: int):
        self.hass = hass
        self.port = port
        self.transport = None
        self.protocol = None
        
    async def start(self) -> None:
        """启动UDP服务器"""
        try:
            loop = asyncio.get_event_loop()
            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: UDPProtocol(self.hass),
                local_addr=('0.0.0.0', self.port)
            )
            _LOGGER.info(f"UDP服务器已启动，监听端口: {self.port}")
        except Exception as e:
            _LOGGER.error(f"启动UDP服务器失败: {e}")
            raise
        
    async def stop(self) -> None:
        """停止UDP服务器"""
        if self.transport:
            self.transport.close()
            _LOGGER.info("UDP服务器已停止")
    
    def get_client_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        if self.protocol:
            return self.protocol.get_client_status()
        return {}

class UDPProtocol(asyncio.DatagramProtocol):
    """UDP协议处理器"""
    
    def __init__(self, hass: HomeAssistant):
        self.hass = hass
        self.known_clients: Dict[str, Dict[str, Any]] = {}
        self._data_parser = ModBusDataParser()
        
    def datagram_received(self, data: bytes, addr: Tuple[str, int]) -> None:
        """接收UDP数据包"""
        try:
            addr_str = f"{addr[0]}:{addr[1]}"
            _LOGGER.debug(f"收到UDP数据包: {len(data)}字节 from {addr_str}")
            
            # 尝试解码数据
            decoded_data = self._decode_data(data)
            if decoded_data is None:
                _LOGGER.warning(f"无法解码UDP数据包 from {addr_str}, 长度: {len(data)}")
                return
            
            # 处理不同类型的数据包
            if self._is_text_packet(decoded_data):
                self._handle_text_packet(decoded_data, addr_str)
            else:
                # 处理风力数据
                self._handle_wind_data_packet(decoded_data, addr_str)
                
        except Exception as e:
            _LOGGER.error(f"处理UDP数据包失败 from {addr}: {e}")
            
    def _decode_data(self, data: bytes) -> Optional[str]:
        """解码数据包"""
        # 优先处理ModBus数据
        modbus_result = self._data_parser.parse_modbus_data(data)
        if modbus_result:
            return modbus_result
        
        # 尝试文本解码
        return self._try_text_decode(data)
    
    def _try_text_decode(self, data: bytes) -> Optional[str]:
        """尝试文本解码"""
        encodings = ['utf-8', 'gbk', 'gb2312', 'ascii', 'latin1']
        
        for encoding in encodings:
            try:
                decoded = data.decode(encoding)
                if encoding != 'utf-8':
                    _LOGGER.debug(f"使用 {encoding} 编码成功解码数据")
                return decoded
            except (UnicodeDecodeError, UnicodeError):
                continue
        
        return None
    
    def _is_text_packet(self, data: str) -> bool:
        """检查是否为文本数据包（心跳包或注册包）"""
        text_indicators = HEARTBEAT_INDICATORS + REGISTRATION_INDICATORS
        data_lower = data.lower()
        return any(indicator in data_lower for indicator in text_indicators)
    
    def _handle_text_packet(self, data: str, addr: str) -> None:
        """处理文本数据包"""
        data_lower = data.lower()
        
        if any(indicator in data_lower for indicator in HEARTBEAT_INDICATORS):
            self._handle_heartbeat(data, addr)
        elif any(indicator in data_lower for indicator in REGISTRATION_INDICATORS):
            self._handle_registration(data, addr)
        else:
            _LOGGER.debug(f"收到未知文本数据包 from {addr}: {data[:50]}")
    
    def _handle_wind_data_packet(self, data: str, addr: str) -> None:
        """处理风力数据包"""
        try:
            json_data = json.loads(data)
            wind_data = json_data.get('wind_data', {})
            
            if wind_data:
                # 更新客户端状态
                self._update_client_status(addr, 'wind_sensor')
                
                # 触发风力数据事件
                self._fire_wind_data_event(wind_data, json_data.get('timestamp'), addr)
                
                # 记录风力数据
                self._log_wind_data(wind_data, addr)
            
        except json.JSONDecodeError:
            _LOGGER.debug(f"收到非JSON风力数据 from {addr}: {data[:50]}")
        except Exception as e:
            _LOGGER.error(f"处理风力数据失败 from {addr}: {e}")
    
    def _fire_wind_data_event(self, wind_data: Dict[str, Any], timestamp: str, addr: str) -> None:
        """触发风力数据事件"""
        event_data = {
            'event_type': 'wind_data_received',
            'wind_data': wind_data,
            'timestamp': timestamp,
            'source_addr': addr
        }
        self.hass.bus.async_fire(f'{DOMAIN}_event', event_data)
    
    def _log_wind_data(self, wind_data: Dict[str, Any], addr: str) -> None:
        """记录风力数据"""
        wind_speed = wind_data.get('0', 0) / WIND_SPEED_SCALE
        wind_direction = wind_data.get('2', 0) / WIND_DIRECTION_SCALE
        wind_level = wind_data.get('1', 0)
        _LOGGER.info(f"风力数据更新 from {addr}: 风速={wind_speed:.1f}m/s, 风向={wind_direction:.1f}°, 风级={wind_level}")
    
    def _handle_heartbeat(self, data: str, addr: str) -> None:
        """处理心跳包"""
        _LOGGER.debug(f"收到心跳包 from {addr}")
        
        self._update_client_status(addr, 'heartbeat')
        
        # 触发心跳事件
        self._fire_heartbeat_event(data, addr)
    
    def _fire_heartbeat_event(self, data: str, addr: str) -> None:
        """触发心跳事件"""
        event_data = {
            'event_type': 'device_heartbeat',
            'device_addr': addr,
            'heartbeat_data': data[:100],
            'timestamp': asyncio.get_event_loop().time()
        }
        self.hass.bus.async_fire(f'{DOMAIN}_event', event_data)
    
    def _handle_registration(self, data: str, addr: str) -> None:
        """处理注册包"""
        _LOGGER.info(f"收到设备注册 from {addr}")
        
        self._update_client_status(addr, 'registration', {'registration_data': data})
        
        # 触发注册事件
        self._fire_registration_event(data, addr)
    
    def _fire_registration_event(self, data: str, addr: str) -> None:
        """触发注册事件"""
        event_data = {
            'event_type': 'device_registered',
            'device_addr': addr,
            'registration_data': data,
            'timestamp': asyncio.get_event_loop().time()
        }
        self.hass.bus.async_fire(f'{DOMAIN}_event', event_data)
    
    def _update_client_status(self, addr: str, client_type: str, extra_data: Optional[Dict] = None) -> None:
        """更新客户端状态"""
        current_time = asyncio.get_event_loop().time()
        
        client_info = {
            'last_seen': current_time,
            'type': client_type
        }
        
        if extra_data:
            client_info.update(extra_data)
        
        # 保留特定的时间戳字段
        if client_type == 'heartbeat':
            client_info['last_heartbeat'] = current_time
        elif client_type == 'registration':
            client_info['last_registration'] = current_time
        
        self.known_clients[addr] = client_info
    
    def get_client_status(self) -> Dict[str, Dict[str, Any]]:
        """获取客户端状态信息"""
        current_time = asyncio.get_event_loop().time()
        status = {}
        
        for addr, info in self.known_clients.items():
            last_seen = info.get('last_seen', 0)
            offline_duration = current_time - last_seen
            
            status[addr] = {
                'type': info.get('type', 'unknown'),
                'last_seen': last_seen,
                'online': offline_duration < OFFLINE_THRESHOLD,
                'offline_duration': offline_duration
            }
        
        return status

class ModBusDataParser:
    """ModBus数据解析器"""
    
    def parse_modbus_data(self, data: bytes) -> Optional[str]:
        """解析ModBus数据"""
        # 检查标准ModBus RTU格式
        if self._is_standard_modbus(data):
            return self._parse_standard_modbus(data)
        
        return None
    
    def _is_standard_modbus(self, data: bytes) -> bool:
        """检查是否为标准ModBus RTU格式"""
        if len(data) < 5:
            return False
        
        device_addr, function_code = data[0], data[1]
        
        if device_addr == MODBUS_DEVICE_ADDR and function_code == MODBUS_FUNCTION_CODE:
            if len(data) >= 3:
                data_length = data[2]
                expected_length = 3 + data_length + 2  # 头部 + 数据 + CRC
                return len(data) == expected_length and data_length == MODBUS_DATA_LENGTH
        
        return False
    
    def _parse_standard_modbus(self, data: bytes) -> Optional[str]:
        """解析标准ModBus RTU数据"""
        try:
            if len(data) < MODBUS_EXPECTED_LENGTH:
                return None
            
            device_addr, function_code, data_length = data[0], data[1], data[2]
            register_data = data[3:11]  # 8字节寄存器数据
            crc = data[11:13]  # CRC校验
            
            _LOGGER.debug(f"ModBus解析: 设备=0x{device_addr:02X}, 功能码=0x{function_code:02X}, "
                         f"数据长度={data_length}, 寄存器={register_data.hex()}, CRC={crc.hex()}")
            
            return self._parse_register_data(register_data)
            
        except Exception as e:
            _LOGGER.error(f"标准ModBus数据解析失败: {e}")
            return None
    
    def _parse_register_data(self, register_data: bytes) -> str:
        """解析寄存器数据"""
        if len(register_data) < 8:
            raise ValueError("寄存器数据长度不足")
        
        # 解析4个寄存器（每个2字节，大端序）
        wind_values = self._extract_wind_values(register_data)
        
        # 构建JSON数据
        wind_json = self._build_wind_json(wind_values)
        
        # 记录解析日志
        self._log_parsed_data(wind_values)
        
        return json.dumps(wind_json)
    
    def _extract_wind_values(self, register_data: bytes) -> Dict[str, int]:
        """从寄存器数据中提取风力数值"""
        return {
            'wind_speed_raw': int.from_bytes(register_data[0:2], 'big'),
            'wind_level': int.from_bytes(register_data[2:4], 'big'),
            'wind_direction_raw': int.from_bytes(register_data[4:6], 'big'),
            'wind_direction_code': int.from_bytes(register_data[6:8], 'big')
        }
    
    def _build_wind_json(self, wind_values: Dict[str, int]) -> Dict[str, Any]:
        """构建风力数据JSON结构"""
        return {
            "wind_data": {
                "0": wind_values['wind_speed_raw'],      # 原始风速值
                "1": wind_values['wind_level'],          # 风级
                "2": wind_values['wind_direction_raw'],  # 原始风向角度值
                "3": wind_values['wind_direction_code']  # 风向编码
            },
            "timestamp": datetime.now().isoformat()
        }
    
    def _log_parsed_data(self, wind_values: Dict[str, int]) -> None:
        """记录解析后的数据"""
        wind_speed_ms = wind_values['wind_speed_raw'] / WIND_SPEED_SCALE
        wind_direction_deg = wind_values['wind_direction_raw'] / WIND_DIRECTION_SCALE
        wind_level = wind_values['wind_level']
        wind_direction_code = wind_values['wind_direction_code']
        
        _LOGGER.debug(f"风力数据解析完成: 风速={wind_speed_ms:.1f}m/s, 风级={wind_level}, "
                     f"风向={wind_direction_deg:.1f}°, 编码=0x{wind_direction_code:02X}")

