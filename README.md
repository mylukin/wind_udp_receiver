# Wind UDP Receiver

[![GitHub stars](https://img.shields.io/github/stars/mylukin/wind_udp_receiver)](https://github.com/mylukin/wind_udp_receiver/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/mylukin/wind_udp_receiver)](https://github.com/mylukin/wind_udp_receiver/network)
[![GitHub issues](https://img.shields.io/github/issues/mylukin/wind_udp_receiver)](https://github.com/mylukin/wind_udp_receiver/issues)
[![License](https://img.shields.io/github/license/mylukin/wind_udp_receiver)](https://github.com/mylukin/wind_udp_receiver/blob/main/LICENSE)

一个用于 Home Assistant 的自定义集成，通过 UDP 协议接收风力传感器数据，支持多种数据格式和实时监控。

## ✨ 功能特性

### 🌪️ 多维度风力监测
- **风速传感器** - 实时监测风速（m/s），自动转换为公里/小时
- **风级传感器** - 基于蒲福风力等级的风级显示（0-12级）
- **风向角度传感器** - 精确的风向角度测量（0-360°）
- **风向编码传感器** - 16方位风向显示（北、东北、东等）
- **设备状态传感器** - 实时监控设备在线状态
- **最后更新传感器** - 显示数据最后更新时间

### 📡 协议支持
- **标准 ModBus 协议** - 支持标准 ModBus UDP 数据包
- **ZQWL 设备协议** - 支持 ZQWL 风力传感器专用协议
- **文本数据包** - 支持心跳包和注册包的文本格式
- **多编码支持** - 自动检测 UTF-8、GBK、GB2312、ASCII 等编码

### 🔧 智能特性
- **时区感知** - 自动适配 Home Assistant 时区设置
- **离线检测** - 自动检测设备离线状态（可配置阈值）
- **设备管理** - 支持多设备同时连接和监控
- **实时事件** - 基于 Home Assistant 事件系统的实时数据更新
- **配置流程** - 支持通过 UI 界面进行配置

## 🚀 安装

### 方法一：HACS 安装（推荐）

1. 确保您已安装 [HACS](https://hacs.xyz/)
2. 在 HACS 中搜索 "Wind UDP Receiver"
3. 点击安装并重启 Home Assistant

### 方法二：手动安装

1. 下载最新版本到 `custom_components` 目录：
```bash
cd /config/custom_components/
git clone https://github.com/mylukin/wind_udp_receiver.git
```

2. 重启 Home Assistant

3. 在 Home Assistant 中添加集成：
   - 进入 **设置** → **设备与服务**
   - 点击 **添加集成**
   - 搜索 "Wind UDP Receiver"

## ⚙️ 配置

### 基本配置

1. **UDP 端口设置**
   - 默认端口：8888
   - 可在配置界面自定义端口

2. **设备连接**
   - 确保风力传感器设备指向正确的 Home Assistant IP 地址和端口
   - 设备应发送 ModBus 或 ZQWL 格式的 UDP 数据包

### 支持的数据格式

#### ModBus 数据格式
```
设备地址: 0x80
功能码: 0x03  
数据长度: 8 字节
数据内容: [风速, 风级, 风向角度, 风向编码] × 2字节
```

#### ZQWL 数据格式
```
包长度: 17 字节
头部: 0x00 0x00 0x00 0x00 0x00 0x0B
数据: 8字节寄存器数据
```

## 📊 传感器详情

| 传感器名称 | 实体ID | 单位 | 描述 |
|-----------|--------|------|------|
| Wind Speed | `sensor.wind_speed` | m/s | 风速测量值 |
| Wind Level | `sensor.wind_level` | 级 | 蒲福风力等级 |
| Wind Direction Angle | `sensor.wind_direction_angle` | ° | 风向角度 (0°=北) |
| Wind Direction Code | `sensor.wind_direction_code` | - | 16方位风向 |
| Device Status | `sensor.wind_device_status` | - | 设备连接状态 |
| Last Update | `sensor.wind_last_update` | - | 最后更新时间 |

### 额外属性

每个传感器还提供丰富的额外属性：

**风速传感器**：
- `wind_speed_ms`: 米/秒风速
- `wind_speed_kmh`: 公里/小时风速  
- `beaufort_scale`: 蒲福风级描述
- `raw_value`: 原始数据值

**风向角度传感器**：
- `angle_degrees`: 角度值
- `cardinal_direction`: 方位名称
- `raw_value`: 原始数据值

**设备状态传感器**：
- `last_activity`: 最后活跃时间
- `offline_duration_seconds`: 离线时长
- `is_online`: 是否在线

## 🛠️ 服务

### `wind_udp_receiver.get_device_status`

获取所有连接设备的详细状态信息，结果将显示在持久化通知中。

```yaml
service: wind_udp_receiver.get_device_status
```

## 📈 自动化示例

### 风速告警
```yaml
automation:
  - alias: "强风告警"
    trigger:
      platform: numeric_state
      entity_id: sensor.wind_speed
      above: 10.8  # 6级强风
    action:
      service: notify.mobile_app_your_phone
      data:
        message: "当前风速 {{ states('sensor.wind_speed') }} m/s，已达到强风级别！"
```

### 设备离线通知
```yaml
automation:
  - alias: "风力传感器离线告警"
    trigger:
      platform: state
      entity_id: sensor.wind_device_status
      to: "离线"
    action:
      service: persistent_notification.create
      data:
        message: "风力传感器已离线，请检查设备连接"
        title: "设备离线告警"
```

## 🔧 故障排除

### 常见问题

1. **设备显示离线**
   - 检查网络连接
   - 确认设备 IP 配置正确
   - 检查防火墙设置

2. **数据不更新**
   - 检查 UDP 端口是否被占用
   - 查看 Home Assistant 日志
   - 确认数据格式是否支持

3. **时间显示错误**
   - 检查 Home Assistant 时区设置
   - 确保系统时间正确

### 日志调试

在 `configuration.yaml` 中启用调试日志：

```yaml
logger:
  default: info
  logs:
    custom_components.wind_udp_receiver: debug
```

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

1. Fork 本项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目基于 MIT 许可证开源 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- 感谢 Home Assistant 社区的支持
- 感谢所有贡献者的努力

---

**⭐ 如果这个项目对你有帮助，请给个 Star！** 