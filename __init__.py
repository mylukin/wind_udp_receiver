import asyncio
import json
import logging
import socket
from datetime import datetime
from typing import Optional, Dict, Any, Tuple

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType
from homeassistant.exceptions import ConfigEntryNotReady

from .const import (
    DOMAIN, PLATFORMS, MODBUS_DEVICE_ADDR, MODBUS_FUNCTION_CODE, 
    MODBUS_DATA_LENGTH, MODBUS_EXPECTED_LENGTH, OFFLINE_THRESHOLD, 
    HEARTBEAT_INDICATORS, REGISTRATION_INDICATORS, WIND_SPEED_SCALE, 
    WIND_DIRECTION_SCALE
)

_LOGGER = logging.getLogger(__name__)

# ================== 入口点函数 ==================

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up from YAML (deprecated)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置集成入口点 - 实现最佳实践的资源管理"""
    _LOGGER.info("正在设置 Wind UDP Receiver 集成")
    
    # 初始化域数据结构
    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    
    port = entry.data.get("port", 8888)
    entry_id = entry.entry_id
    
    try:
        # 检查并清理已存在的实例
        await _cleanup_existing_instance(hass, entry_id, port)
        
        # 检查端口可用性
        _LOGGER.debug(f"检查端口 {port} 可用性...")
        if not await _check_port_available(port):
            _LOGGER.error(f"端口 {port} 被占用，无法启动服务")
            raise ConfigEntryNotReady(f"端口 {port} 不可用")
        _LOGGER.debug(f"端口 {port} 检查通过")
        
        # 创建并启动UDP服务器
        udp_server = UDPWindServer(hass, port)
        await udp_server.start()
        
        # 保存服务器实例
        hass.data[DOMAIN][entry_id] = {
            "server": udp_server,
            "port": port,
            "entry": entry
        }
        
        # 注册服务
        await _register_services(hass, udp_server)
        
        # 设置传感器平台
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        
        _LOGGER.info(f"Wind UDP Receiver 设置完成，端口: {port}")
        return True
        
    except ConfigEntryNotReady:
        # 重新抛出ConfigEntryNotReady异常
        raise
    except Exception as e:
        _LOGGER.error(f"设置 Wind UDP Receiver 失败: {e}")
        # 确保清理部分创建的资源
        await _cleanup_failed_setup(hass, entry_id)
        raise ConfigEntryNotReady(f"设置失败: {e}")

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目 - 确保完全清理资源"""
    entry_id = entry.entry_id
    _LOGGER.info(f"开始卸载 Wind UDP Receiver (entry_id: {entry_id})")
    
    try:
        # 获取并清理服务器实例
        server_data = hass.data[DOMAIN].get(entry_id)
        if server_data:
            udp_server = server_data.get("server")
            if udp_server:
                await udp_server.stop()
                _LOGGER.debug("UDP服务器已停止")
            
            # 从数据字典中移除
            hass.data[DOMAIN].pop(entry_id, None)
        
        # 移除服务（只在没有其他实例时）
        if not hass.data[DOMAIN]:  # 如果没有其他实例了
            if hass.services.has_service(DOMAIN, "get_device_status"):
                hass.services.async_remove(DOMAIN, "get_device_status")
                _LOGGER.debug("已移除设备状态服务")
        
        # 卸载平台
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            _LOGGER.info("Wind UDP Receiver 已成功卸载")
        else:
            _LOGGER.warning("Wind UDP Receiver 卸载过程中出现警告")
            
        return unload_ok
        
    except Exception as e:
        _LOGGER.error(f"卸载 Wind UDP Receiver 失败: {e}")
        return False

# ================== 资源管理辅助函数 ==================

async def _cleanup_existing_instance(hass: HomeAssistant, entry_id: str, port: int) -> None:
    """清理已存在的实例"""
    try:
        # 检查是否有相同entry_id的实例
        existing_data = hass.data.get(DOMAIN, {}).get(entry_id)
        if existing_data:
            _LOGGER.warning(f"发现已存在的实例 (entry_id: {entry_id})，正在清理...")
            existing_server = existing_data.get("server")
            if existing_server:
                await existing_server.stop()
            hass.data[DOMAIN].pop(entry_id, None)
            _LOGGER.info("已清理旧实例")
        
        # 检查是否有相同端口的实例
        for existing_entry_id, data in list(hass.data.get(DOMAIN, {}).items()):
            if data.get("port") == port and existing_entry_id != entry_id:
                _LOGGER.warning(f"发现端口 {port} 被其他实例占用 (entry_id: {existing_entry_id})，正在清理...")
                existing_server = data.get("server")
                if existing_server:
                    await existing_server.stop()
                hass.data[DOMAIN].pop(existing_entry_id, None)
                _LOGGER.info(f"已清理端口冲突的实例: {existing_entry_id}")
                
    except Exception as e:
        _LOGGER.error(f"清理已存在实例时出错: {e}")

async def _check_port_available(port: int) -> bool:
    """检查端口是否可用"""
    sock = None
    try:
        # 尝试绑定UDP端口
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        # 尝试设置 SO_REUSEPORT（如果可用）
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except (AttributeError, OSError):
            # SO_REUSEPORT 在某些系统上不可用，忽略
            pass
        
        sock.bind(('0.0.0.0', port))
        _LOGGER.debug(f"端口 {port} 可用")
        return True
        
    except OSError as e:
        _LOGGER.debug(f"端口 {port} 不可用: {e}")
        return False
    except Exception as e:
        _LOGGER.error(f"检查端口可用性时出错: {e}")
        return False
    finally:
        if sock:
            try:
                sock.close()
            except:
                pass

async def _cleanup_failed_setup(hass: HomeAssistant, entry_id: str) -> None:
    """清理失败的设置过程中创建的资源"""
    try:
        if DOMAIN in hass.data and entry_id in hass.data[DOMAIN]:
            server_data = hass.data[DOMAIN].get(entry_id)
            if server_data and "server" in server_data:
                await server_data["server"].stop()
            hass.data[DOMAIN].pop(entry_id, None)
            _LOGGER.debug(f"已清理失败设置的资源: {entry_id}")
    except Exception as e:
        _LOGGER.error(f"清理失败设置资源时出错: {e}")

# ================== 服务注册 ==================

async def _register_services(hass: HomeAssistant, udp_server: 'UDPWindServer') -> None:
    """注册Home Assistant服务"""
    
    # 检查服务是否已注册（支持多实例）
    if hass.services.has_service(DOMAIN, "get_device_status"):
        _LOGGER.debug("设备状态服务已存在，跳过注册")
        return
    
    async def get_device_status(call):
        """获取设备状态服务"""
        try:
            # 获取所有实例的状态
            all_status = {}
            for entry_id, data in hass.data.get(DOMAIN, {}).items():
                server = data.get("server")
                if server:
                    port = data.get("port", "未知")
                    status = server.get_client_status()
                    all_status[f"端口{port}"] = status
            
            message = _format_device_status_message(all_status)
            
            await hass.services.async_call(
                'persistent_notification', 'create',
                {'message': message, 'title': 'Wind UDP Receiver 设备状态'}
            )
            _LOGGER.debug(f"设备状态查询结果: {len(all_status)} 个端口")
        except Exception as e:
            _LOGGER.error(f"获取设备状态失败: {e}")
    
    hass.services.async_register(DOMAIN, "get_device_status", get_device_status)
    _LOGGER.debug("已注册设备状态服务")

def _format_device_status_message(all_status: Dict[str, Dict[str, Any]]) -> str:
    """格式化设备状态消息"""
    if not all_status:
        return "设备状态:\n暂无设备连接"
    
    message = "设备状态:\n"
    for port_info, status in all_status.items():
        message += f"\n{port_info}:\n"
        if not status:
            message += "  暂无设备连接\n"
        else:
            for addr, info in status.items():
                online_status = "在线" if info['online'] else f"离线({info['offline_duration']:.0f}秒)"
                device_type = info.get('type', '未知')
                message += f"  设备 {addr}: {online_status} ({device_type})\n"
    
    return message

class UDPWindServer:
    """UDP风力传感器服务器 - 增强版本，支持优雅重启"""
    
    def __init__(self, hass: HomeAssistant, port: int):
        self.hass = hass
        self.port = port
        self.transport = None
        self.protocol = None
        self._running = False
        self._start_lock = asyncio.Lock()
        
    async def start(self) -> None:
        """启动UDP服务器，带重试机制"""
        async with self._start_lock:
            if self._running:
                _LOGGER.warning(f"UDP服务器已在端口 {self.port} 运行")
                return
                
            max_retries = 3
            retry_delay = 1.0
            
            for attempt in range(max_retries):
                sock = None
                try:
                    _LOGGER.debug(f"尝试启动UDP服务器，端口: {self.port} (尝试 {attempt + 1}/{max_retries})")
                    
                    # 创建UDP套接字并设置重用选项
                    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    
                    # 在某些系统上需要设置 SO_REUSEPORT
                    try:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                    except (AttributeError, OSError):
                        # SO_REUSEPORT 在某些系统上不可用，忽略
                        pass
                    
                    # 绑定到指定端口
                    sock.bind(('0.0.0.0', self.port))
                    
                    # 使用预先配置的套接字创建数据报端点
                    loop = asyncio.get_event_loop()
                    self.transport, self.protocol = await loop.create_datagram_endpoint(
                        lambda: UDPProtocol(self.hass),
                        sock=sock
                    )
                    
                    self._running = True
                    _LOGGER.info(f"UDP服务器已启动，监听端口: {self.port}")
                    return
                    
                except OSError as e:
                    if sock:
                        try:
                            sock.close()
                        except:
                            pass
                    
                    error_msg = str(e).lower()
                    if any(msg in error_msg for msg in ["address already in use", "only one usage", "permission denied"]):
                        _LOGGER.warning(f"端口 {self.port} 启动失败: {e} (尝试 {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            _LOGGER.debug(f"等待 {retry_delay} 秒后重试...")
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2  # 指数退避
                        else:
                            raise ConfigEntryNotReady(f"端口 {self.port} 无法启动: {e}")
                    else:
                        _LOGGER.error(f"UDP服务器启动失败 (非端口问题): {e}")
                        raise
                except Exception as e:
                    if sock:
                        try:
                            sock.close()
                        except:
                            pass
                    _LOGGER.error(f"启动UDP服务器失败: {e}")
                    if attempt == max_retries - 1:
                        raise ConfigEntryNotReady(f"UDP服务器启动失败: {e}")
                    _LOGGER.debug(f"等待 {retry_delay} 秒后重试...")
                    await asyncio.sleep(retry_delay)
        
    async def stop(self) -> None:
        """停止UDP服务器，确保完全清理"""
        async with self._start_lock:
            if not self._running:
                _LOGGER.debug("UDP服务器未运行，无需停止")
                return
                
            try:
                if self.transport:
                    _LOGGER.debug("正在关闭UDP传输...")
                    self.transport.close()
                    
                    # 等待传输完全关闭
                    max_wait = 5.0  # 最多等待5秒
                    wait_time = 0.1
                    total_waited = 0
                    
                    while not self.transport.is_closing() and total_waited < max_wait:
                        await asyncio.sleep(wait_time)
                        total_waited += wait_time
                    
                    if total_waited >= max_wait:
                        _LOGGER.warning("UDP传输关闭超时")
                    else:
                        _LOGGER.debug(f"UDP传输已关闭 (等待时间: {total_waited:.2f}s)")
                
                self.transport = None
                self.protocol = None
                self._running = False
                
                # 额外等待，确保端口释放
                await asyncio.sleep(0.5)
                
                _LOGGER.info(f"UDP服务器已停止，端口 {self.port} 已释放")
                
            except Exception as e:
                _LOGGER.error(f"停止UDP服务器时出错: {e}")
                # 即使出错也要标记为已停止
                self._running = False
                self.transport = None
                self.protocol = None
    
    def get_client_status(self) -> Dict[str, Any]:
        """获取客户端状态"""
        if not self._running or not self.protocol:
            return {}
        return self.protocol.get_client_status()
    
    @property
    def is_running(self) -> bool:
        """检查服务器是否正在运行"""
        return self._running and self.transport is not None

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

