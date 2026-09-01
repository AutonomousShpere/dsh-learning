---
name: weather
description: 查询指定地点的当前天气以及未来三天天气预报，包括温度、体感温度、湿度、风速和风向。
---

# 天气查询

当用户询问当前天气、温度、湿度、风速、风向、体感温度或未来三天天气时，使用此 Skill。

天气数据使用 Open-Meteo 获取（免费，无需 API Key）。

## 1. 确定地点

1. 如果用户指定了地点，使用用户指定的地点。
2. 如果用户没有指定地点，直接询问用户所在的城市或地区。
3. 如果地点存在明显歧义（例如同名城市），不要猜测，要求用户进一步说明城市、州/省或国家。

## 2. 将地点转换为经纬度

使用 Open-Meteo Geocoding API 查询地点。

- `language` 参数应跟随用户提问使用的语言：中文用户用 `language=zh`，英文用户用 `language=en`，这样返回的 `name`、`country`、`admin1` 才会以用户的语言呈现。
- 查询中文地点时，URL 中的非 ASCII 字符需要做 URL 编码，建议用 `curl -G --data-urlencode`（比手写 `name=北京` 更稳妥）。

中文地点示例：

```bash
curl -sG "https://geocoding-api.open-meteo.com/v1/search" \
  --data-urlencode "name=北京" \
  --data "count=5" \
  --data "language=zh" \
  --data "format=json"
```

英文地点示例：

```bash
curl -s "https://geocoding-api.open-meteo.com/v1/search?name=Canberra&count=5&language=en&format=json"
```

实际查询时，将地点替换为用户要求查询的地点。

从返回的 `results[0]`（或与用户意图最匹配的那一条）中获取：

- 地点名称 `name`
- 纬度 `latitude`
- 经度 `longitude`
- 国家或地区 `country`（用于消歧与展示）

处理：

- 如果 `results` 为空，告诉用户无法识别该地点。
- 如果返回多个合理匹配，且无法确定用户指哪一个，列出候选（含 `name`、`admin1`、`country`）并请用户确认。

### 区/县级地点（含街道、镇）

查询区、县、街道、镇等更细的行政层级时，Open-Meteo Geocoding 对中文"区"名覆盖不全、匹配不稳定，按以下顺序处理：

1. **先用 Open-Meteo 查（去后缀）**：去掉行政后缀（`区`/`县`/`新区`/`镇`/`乡`/`街道`）后用裸名查，例如 `海淀区` → 查 `海淀`。**不要用"城市 + 区"拼接**（如 `海淀 北京`），实测会返回空。
   - 用 `feature_code` 判断层级：`PPLA3` = 区/县，`PPLA4` = 街道/镇（`PPLA2` = 地级市）。
   - 同名结果较多时，用 `admin1`（省）、`admin2`（市）与用户上下文匹配；仍不确定就列候选让用户确认。
2. **查不到时改用 Nominatim（OpenStreetMap）兜底**：Open-Meteo 数据集里缺少部分区（实测 `北京朝阳区`、`深圳福田区` 查不到），此时用 Nominatim 的整串查询：

```bash
curl -s -H "User-Agent: dsh-weather-skill/1.0" "https://nominatim.openstreetmap.org/search?q=北京市海淀区&format=json&limit=3&accept-language=zh"
```

   将 `q=` 后的地点换成"城市 + 区"的完整写法（Nominatim 支持这种整串查询）。从返回结果里选 `type` 为 `administrative`（行政区）的那条，取 `lat` 和 `lon`。
3. **两者都查不到时**：降级使用上一级城市的坐标，并明确告知用户"当前只能精确到市级"。

> 说明：Nominatim 要求请求携带自定义 `User-Agent`（上面已带），且是公共服务、有速率限制，请勿高频批量请求。得到的 `lat`/`lon` 与 Open-Meteo 的结果一样，都直接用于第 3 步的 Forecast API。

## 3. 查询天气

得到 `latitude` 和 `longitude` 后，使用 Open-Meteo Forecast API 查询天气。

示例（Canberra）：

```bash
curl -s "https://api.open-meteo.com/v1/forecast?latitude=-35.28&longitude=149.13&current=temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m&daily=weather_code,temperature_2m_max,temperature_2m_min&forecast_days=4&timezone=auto&temperature_unit=celsius&wind_speed_unit=kmh"
```

实际查询时：

- 将 `latitude`、`longitude` 替换为第 2 步得到的值。
- `timezone=auto`：按查询地点的当地时间处理天气数据。
- `forecast_days=4`：返回「当天 + 未来 3 天」的 daily 数据。
- `temperature_unit=celsius`、`wind_speed_unit=kmh`：显式指定单位，避免默认值变动导致歧义（湿度单位为 `%`，无对应参数）。
- daily 数组第 1 条（`daily.time[0]`）是当天，展示「未来三天」时跳过它，只取接下来的 3 个日期。

## 4. 当前天气

从 `current` 读取：

- `temperature_2m`：当前温度（°C）
- `apparent_temperature`：体感温度（°C）
- `relative_humidity_2m`：相对湿度（%）
- `weather_code`：当前天气状况（用第 6 节表转换）
- `wind_speed_10m`：风速（km/h）
- `wind_direction_10m`：风向（角度，用第 7 节表转换）

## 5. 未来三天天气

从 `daily` 读取：

- `time`：日期（`YYYY-MM-DD`）
- `weather_code`：天气状况
- `temperature_2m_max`：最高温度（°C）
- `temperature_2m_min`：最低温度（°C）

跳过当天（`daily.time[0]`），只显示接下来的 3 个日期。

## 6. 天气代码解释

将 `weather_code`（WMO 代码）转换为用户易懂的描述：

| 代码 | 描述 |
|---|---|
| 0 | 晴 |
| 1 | 大致晴朗 |
| 2 | 局部多云 |
| 3 | 阴 |
| 45 | 雾 |
| 48 | 雾凇雾 |
| 51 | 轻毛毛雨 |
| 53 | 中毛毛雨 |
| 55 | 浓毛毛雨 |
| 56 | 轻冻毛毛雨 |
| 57 | 浓冻毛毛雨 |
| 61 | 小雨 |
| 63 | 中雨 |
| 65 | 大雨 |
| 66 | 轻冻雨 |
| 67 | 大冻雨 |
| 71 | 小雪 |
| 73 | 中雪 |
| 75 | 大雪 |
| 77 | 雪粒 |
| 80 | 小阵雨 |
| 81 | 中阵雨 |
| 82 | 强阵雨 |
| 85 | 小阵雪 |
| 86 | 大阵雪 |
| 95 | 雷暴（轻微/中等） |
| 96 | 雷暴伴小冰雹 |
| 99 | 雷暴伴大冰雹 |

回答时不要显示原始天气代码数字；若用户使用英文提问，改用对应的英文描述（clear sky、partly cloudy、overcast、light rain 等）。

## 7. 风向解释

`wind_direction_10m` 返回角度（0°–360°，0° 表示北风，顺时针增加）。

按下表把角度转成方位（使用半开区间 `[起点, 终点)`，消除边界歧义）：

- `[337.5, 360)` 或 `[0, 22.5)`：北风
- `[22.5, 67.5)`：东北风
- `[67.5, 112.5)`：东风
- `[112.5, 157.5)`：东南风
- `[157.5, 202.5)`：南风
- `[202.5, 247.5)`：西南风
- `[247.5, 292.5)`：西风
- `[292.5, 337.5)`：西北风

回答时同时显示风速，例如：

`西北风，18 km/h`

## 8. 回答格式

优先使用用户提问时使用的语言；日期等本地化内容也随之调整。

推荐格式（单位一并标注）：

### 当前天气

- 地点：{地点名称}
- 天气：{天气状况}
- 温度：{当前温度} °C
- 体感温度：{体感温度} °C
- 湿度：{相对湿度} %
- 风向：{风向}
- 风速：{风速} km/h

### 未来三天

**{日期 1}**
- 天气：{天气状况}
- 最高温度：{最高温度} °C
- 最低温度：{最低温度} °C

**{日期 2}**
- 天气：{天气状况}
- 最高温度：{最高温度} °C
- 最低温度：{最低温度} °C

**{日期 3}**
- 天气：{天气状况}
- 最高温度：{最高温度} °C
- 最低温度：{最低温度} °C

## 9. 错误处理

- 地点无法识别：不要猜测，请用户补充说明。
- 天气 API 请求失败（HTTP 非 200 或返回非法 JSON）：明确告诉用户天气数据获取失败，可建议稍后重试。
- 某个字段缺失：不要编造数据，省略该字段即可。
- 不要向普通用户展示原始 JSON、经纬度、API 地址或天气代码数字，除非用户明确要求查看技术信息。
