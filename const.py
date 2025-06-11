"""Wind UDP Receiver 常量定义"""

# 集成域名
DOMAIN = "wind_udp_receiver"

# 平台列表
PLATFORMS = ["sensor"]

# ModBus 协议配置
MODBUS_DEVICE_ADDR = 0x80
MODBUS_FUNCTION_CODE = 0x03
MODBUS_DATA_LENGTH = 8
MODBUS_EXPECTED_LENGTH = 13  # 3字节头部 + 8字节数据 + 2字节CRC

# 客户端状态配置
OFFLINE_THRESHOLD = 60  # 统一离线阈值 (秒)

# 数据转换配置
WIND_SPEED_SCALE = 10.0     # 风速除数因子
WIND_DIRECTION_SCALE = 10.0  # 风向除数因子

# 风向编码映射 - 基于传感器手册16方位图
WIND_DIRECTION_MAP = {
    0x00: "北", 0x01: "北东北", 0x02: "东北", 0x03: "东东北",
    0x04: "东", 0x05: "东东南", 0x06: "东南", 0x07: "南东南", 
    0x08: "南", 0x09: "南西南", 0x0A: "西南", 0x0B: "西西南",
    0x0C: "西", 0x0D: "西西北", 0x0E: "西北", 0x0F: "北西北"
}

# 风级描述映射
WIND_LEVEL_MAP = {
    0: "无风", 1: "软风", 2: "轻风", 3: "微风", 4: "和风", 5: "清劲风",
    6: "强风", 7: "疾风", 8: "大风", 9: "烈风", 10: "狂风", 11: "暴风", 12: "飓风"
}

# 蒲福风级阈值 (m/s)
BEAUFORT_SCALE_THRESHOLDS = [
    (0.3, "0级 (无风)"), (1.6, "1级 (软风)"), (3.4, "2级 (轻风)"), (5.5, "3级 (微风)"),
    (8.0, "4级 (和风)"), (10.8, "5级 (清劲风)"), (13.9, "6级 (强风)"), (17.2, "7级 (疾风)"),
    (20.8, "8级 (大风)"), (24.5, "9级 (烈风)"), (28.5, "10级 (狂风)"), (32.7, "11级 (暴风)")
]

# 16方位角度范围 (度数, 方位名称)
DIRECTION_ANGLE_RANGES = [
    (11.25, "北"), (33.75, "北东北"), (56.25, "东北"), (78.75, "东东北"),
    (101.25, "东"), (123.75, "东东南"), (146.25, "东南"), (168.75, "南东南"),
    (191.25, "南"), (213.75, "南西南"), (236.25, "西南"), (258.75, "西西南"),
    (281.25, "西"), (303.75, "西西北"), (326.25, "西北"), (348.75, "北西北")
]

# 文本数据包指示符
HEARTBEAT_INDICATORS = [
    'heartbeat', 'ping', 'alive', 'keep-alive', 'heart_beat', 'keepalive'
]

REGISTRATION_INDICATORS = [
    'register', 'registration', 'connect', 'login', 'device_info', 'client_info'
]

# 默认配置
DEFAULT_CONFIG = {
    'port': 8888,
    'encoding': 'utf-8'
} 