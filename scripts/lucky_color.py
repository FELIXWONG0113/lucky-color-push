# -*- coding: utf-8 -*-
"""
每日幸运色微信推送脚本
- 主数据源1：问运势网五行穿衣指南
- 主数据源2：pmdy.cn（备用，问运势网不可用时自动切换）
- 算法备用：基于天干地支五行生克自动计算（网站都不可用时使用）
- 推送渠道：PushPlus → 微信
"""

import os
import sys
import re
import json
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

# ===== 常量 =====

PUSHPLUS_API = "http://www.pushplus.plus/send"
BJT = timezone(timedelta(hours=8))

# 通用请求头（更完整，减少被拦截概率）
COMMON_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "keep-alive",
}

# 颜色名称 → CSS 颜色值映射
COLOR_MAP = {
    "黑色": "#000000",
    "蓝色": "#0066cc",
    "白色": "#ffffff",
    "银色": "#c0c0c0",
    "金黄": "#ffd700",
    "米白": "#f5f5dc",
    "灰色": "#808080",
    "红色": "#dc3545",
    "紫色": "#6f42c1",
    "粉色": "#e83e8c",
    "橙红": "#ff6347",
    "绿色": "#28a745",
    "青色": "#17a2b8",
    "苍青": "#2e8b57",
    "青绿": "#20c997",
    "翠绿": "#00d084",
    "黄色": "#ffc107",
    "咖色": "#8b4513",
    "棕色": "#a0522d",
    "褐色": "#800000",
    "米黄": "#f0e68c",
    "驼色": "#c19a6b",
    "橙黄": "#fd7e14",
}

# 五行 → 颜色系映射
WUXING_COLORS = {
    "金": ["白色", "银色", "灰色", "米白"],
    "木": ["绿色", "青色", "苍青", "翠绿"],
    "水": ["黑色", "蓝色"],
    "火": ["红色", "紫色", "粉色", "橙红"],
    "土": ["黄色", "咖色", "棕色", "褐色", "橙黄"],
}

# 五行相生：A生B → A → B
SHENG = {"木": "火", "火": "土", "土": "金", "金": "水", "水": "木"}

# 五行相克：A克B → A → B
KE = {"金": "木", "木": "土", "土": "水", "水": "火", "火": "金"}

# 地支 → 五行
DIZHI_WUXING = {
    "子": "水", "丑": "土", "寅": "木", "卯": "木",
    "辰": "土", "巳": "火", "午": "火", "未": "土",
    "申": "金", "酉": "金", "戌": "土", "亥": "水",
}

# 天干 → 五行
TIANGAN_WUXING = {
    "甲": "木", "乙": "木", "丙": "火", "丁": "火",
    "戊": "土", "己": "土", "庚": "金", "辛": "金",
    "壬": "水", "癸": "水",
}

# 天干列表（用于计算日柱）
TIANGAN_LIST = ["甲", "乙", "丙", "丁", "戊", "己", "庚", "辛", "壬", "癸"]
DIZHI_LIST = ["子", "丑", "寅", "卯", "辰", "巳", "午", "未", "申", "酉", "戌", "亥"]

# 颜色等级配置
LEVEL_CONFIG = {
    "daji":     {"label": "大吉 · 贵人色"},
    "ciji":     {"label": "次吉 · 合作色"},
    "pingping": {"label": "平平 · 招财色"},
    "shenyong": {"label": "慎用 · 消耗色"},
    "jiyong":   {"label": "忌用 · 不利色"},
}


# ===== 数据爬取 =====

def fetch_wenyunshi(date_str):
    """爬取问运势网五行穿衣数据"""
    url = f"https://www.wenyunshi.com/sm/wuxingchuanyi/{date_str}.html"
    headers = {**COMMON_HEADERS, "Referer": "https://www.wenyunshi.com/sm/wuxingchuanyi/"}

    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"

    if resp.status_code != 200:
        raise Exception(f"问运势网请求失败，状态码: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    data = {}

    # 1. 日期信息
    solar_el = soup.select_one(".solar-date")
    lunar_el = soup.select_one(".lunar-date")
    data["solar_date"] = solar_el.get_text(strip=True) if solar_el else date_str
    data["lunar_date"] = lunar_el.get_text(strip=True) if lunar_el else ""

    # 2. 干支信息
    ganzhi = {}
    for item in soup.select(".wuxing-item"):
        label_el = item.select_one(".item-label")
        value_el = item.select_one(".item-value")
        if label_el and value_el:
            ganzhi[label_el.get_text(strip=True)] = value_el.get_text(strip=True)
    data["ganzhi"] = ganzhi

    # 3. 五个颜色等级
    colors = {}
    for class_name, config in LEVEL_CONFIG.items():
        block = soup.select_one(f".color-recommend.{class_name}")
        if not block:
            colors[class_name] = {"label": config["label"], "effect": "", "colors": [], "yuyi": ""}
            continue

        color_names = [cn.get_text(strip=True) for cn in block.select(".color-name")]
        effect_el = block.select_one(".recommend-effect")
        effect = effect_el.get_text(strip=True) if effect_el else ""
        yuyi_el = block.select_one(".yuyi-text")
        yuyi = yuyi_el.get_text(strip=True) if yuyi_el else ""

        colors[class_name] = {"label": config["label"], "effect": effect, "colors": color_names, "yuyi": yuyi}
    data["colors"] = colors

    # 4. 宜忌
    yi_items = [s.get_text(strip=True) for s in soup.select(".yi-items span")]
    ji_items = [s.get_text(strip=True) for s in soup.select(".ji-items span")]
    data["yi"] = yi_items
    data["ji"] = ji_items

    # 5. 五行相生相克
    sheng_el = soup.select_one(".sheng")
    ke_el = soup.select_one(".ke")
    data["sheng"] = sheng_el.get_text(strip=True) if sheng_el else ""
    data["ke"] = ke_el.get_text(strip=True) if ke_el else ""

    data["source"] = "问运势网"
    return data


def fetch_pmdy(date_str):
    """爬取 pmdy.cn 五行穿衣数据（备用数据源）"""
    url = f"https://www.pmdy.cn/day/{date_str}.html"
    headers = {**COMMON_HEADERS, "Referer": "https://www.pmdy.cn/"}

    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"

    if resp.status_code != 200:
        raise Exception(f"pmdy.cn请求失败，状态码: {resp.status_code}")

    soup = BeautifulSoup(resp.text, "html.parser")
    text = soup.get_text(separator="")  # 纯文本，无换行，便于正则连续匹配

    data = {}

    # 用正则解析纯文本格式的颜色数据
    # 格式: 1、大吉色（贵人色）：白色、银色、灰色、米白，解释：...
    patterns = {
        "daji":     r"1[、.]\s*大吉色[^：]*[：:]\s*([^，,解释]+)",
        "ciji":     r"2[、.]\s*次吉色[^：]*[：:]\s*([^，,寓意]+)",
        "pingping": r"3[、.]\s*平平色[^：]*[：:]\s*([^，,寓意]+)",
        "shenyong": r"4[、.]\s*慎用色[^：]*[：:]\s*([^，,寓意]+)",
        "jiyong":   r"5[、.]\s*忌用色[^：]*[：:]\s*([^，,寓意]+)",
    }

    colors = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            color_str = match.group(1).strip()
            color_names = [c.strip() for c in color_str.split("、") if c.strip()]
        else:
            color_names = []
        colors[key] = {"label": LEVEL_CONFIG[key]["label"], "effect": "", "colors": color_names, "yuyi": ""}
    data["colors"] = colors

    # 解析日期信息
    date_match = re.search(r"今天是公历[：:]\s*(\d+年\d+月\d+日)", text)
    lunar_match = re.search(r"农历[：:]\s*([二〇一二三四五六七八九十]+月[初正一二三四五六七八九十]+)", text)
    ganzhi_match = re.search(r"天干地支为[：:]\s*([\u4e00-\u9fff]+年[\u4e00-\u9fff]+月[\u4e00-\u9fff]+日)", text)

    data["solar_date"] = date_match.group(1) if date_match else date_str
    data["lunar_date"] = lunar_match.group(1) if lunar_match else ""

    # 解析干支
    ganzhi = {}
    if ganzhi_match:
        gz_str = ganzhi_match.group(1)
        gz_parts = re.findall(r"([\u4e00-\u9fff]{2,3})", gz_str)
        if len(gz_parts) >= 3:
            ganzhi["干支年柱"] = gz_parts[0]
            ganzhi["干支月柱"] = gz_parts[1]
            ganzhi["干支日柱"] = gz_parts[2]

    # 日干五行
    wuxing_match = re.search(r"日地支五行为[：:]\s*([\u4e00-\u9fff]+)", text)
    if wuxing_match:
        ganzhi["日干五行"] = wuxing_match.group(1)
    data["ganzhi"] = ganzhi

    # 解析宜忌
    yi_match = re.search(r"今日黄历宜[：:]\s*([^\n<>]+)", text)
    ji_match = re.search(r"今日黄历忌[：:]\s*([^\n<>]+)", text)
    data["yi"] = yi_match.group(1).strip().split() if yi_match else []
    data["ji"] = ji_match.group(1).strip().split() if ji_match else []

    # 大吉寓意：从"解释："起，到下一个编号段落或末尾
    yuyi_match = re.search(r"解释[：:](.+?)(?:\n+\d[、.]|$)", text, re.DOTALL)
    if yuyi_match:
        raw_yuyi = yuyi_match.group(1).strip()
        # 清理多余换行，截取前80字
        raw_yuyi = re.sub(r'\s+', '', raw_yuyi)
        if len(raw_yuyi) > 80:
            raw_yuyi = raw_yuyi[:80] + "..."
        colors["daji"]["yuyi"] = raw_yuyi

    data["sheng"] = ""
    data["ke"] = ""
    data["source"] = "pmdy.cn"
    return data


def calculate_wuxing_algorithmically(date_str):
    """基于天干地支五行生克理论，纯算法计算幸运色（终极备用）"""
    try:
        parts = date_str.split("-")
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
    except (ValueError, IndexError):
        raise Exception(f"日期格式错误: {date_str}")

    # 计算日柱的天干地支
    # 基于已知基准日：2024年1月1日 = 甲子日（干支序号0）
    # 实际使用一个可靠的基准：2000年1月7日为甲子日
    base_date = datetime(2000, 1, 7)
    target_date = datetime(year, month, day)
    days_diff = (target_date - base_date).days

    # 干支60甲子循环
    ganzhi_index = days_diff % 60
    tiangan_index = ganzhi_index % 10
    dizhi_index = ganzhi_index % 12

    day_tiangan = TIANGAN_LIST[tiangan_index]
    day_dizhi = DIZHI_LIST[dizhi_index]
    day_wuxing = DIZHI_WUXING[day_dizhi]

    # 根据五行生克规则确定各等级颜色
    # 大吉：被当日五行生 → 当日五行所生的元素
    daji_wuxing = SHENG[day_wuxing]
    # 次吉：与当日五行同 → 同元素
    ciji_wuxing = day_wuxing
    # 平平：克当日五行 → 能克制当日五行的元素
    pingping_wuxing = None
    for wx, target in KE.items():
        if target == day_wuxing:
            pingping_wuxing = wx
            break
    # 慎用：生当日五行 → 生成当日五行的元素（消耗）
    shenyong_wuxing = None
    for wx, target in SHENG.items():
        if target == day_wuxing:
            shenyong_wuxing = wx
            break
    # 忌用：被当日五行克 → 当日五行所克制的元素
    jiyong_wuxing = KE[day_wuxing]

    colors = {
        "daji":     {"label": LEVEL_CONFIG["daji"]["label"], "effect": "", "colors": WUXING_COLORS[daji_wuxing], "yuyi": f"五行{day_wuxing}生{daji_wuxing}，易获贵人扶助，事半功倍"},
        "ciji":     {"label": LEVEL_CONFIG["ciji"]["label"], "effect": "", "colors": WUXING_COLORS[ciji_wuxing], "yuyi": f"与当日五行同属{ciji_wuxing}，幸运眷顾，行事顺利"},
        "pingping": {"label": LEVEL_CONFIG["pingping"]["label"], "effect": "", "colors": WUXING_COLORS[pingping_wuxing] if pingping_wuxing else [], "yuyi": ""},
        "shenyong": {"label": LEVEL_CONFIG["shenyong"]["label"], "effect": "", "colors": WUXING_COLORS[shenyong_wuxing] if shenyong_wuxing else [], "yuyi": ""},
        "jiyong":   {"label": LEVEL_CONFIG["jiyong"]["label"], "effect": "", "colors": WUXING_COLORS[jiyong_wuxing] if jiyong_wuxing else [], "yuyi": ""},
    }

    # 干支信息
    ganzhi = {
        "干支日柱": f"{day_tiangan}{day_dizhi}",
        "日干五行": day_wuxing,
    }

    data = {
        "solar_date": f"{year}年{month}月{day}日",
        "lunar_date": "",
        "ganzhi": ganzhi,
        "colors": colors,
        "yi": [],
        "ji": [],
        "sheng": f"{day_wuxing}生{daji_wuxing}",
        "ke": f"{day_wuxing}克{jiyong_wuxing}",
        "source": "算法计算",
    }
    return data


def fetch_wuxing_data(date_str):
    """尝试多个数据源获取五行穿衣数据，自动容错切换"""
    sources = [
        ("问运势网", fetch_wenyunshi),
        ("pmdy.cn", fetch_pmdy),
        ("算法计算", calculate_wuxing_algorithmically),
    ]

    for source_name, fetch_func in sources:
        try:
            print(f"[INFO] 尝试数据源: {source_name}...")
            data = fetch_func(date_str)
            print(f"[OK] {source_name} 数据获取成功: {data.get('solar_date', date_str)}")
            return data
        except Exception as e:
            print(f"[WARN] {source_name} 获取失败: {e}")
            continue

    raise Exception("所有数据源均获取失败")


# ===== HTML 消息生成（极简风格 - 参考iOS卡片设计） =====


def small_color_dot(name):
    """小圆点备选色"""
    hex_val = COLOR_MAP.get(name, "#cccccc")
    light_colors = ("#ffffff", "#f5f5dc", "#c0c0c0")
    shadow = "box-shadow:0 2px 6px rgba(0,0,0,0.15);" if hex_val not in light_colors else \
             "border:1px solid #e0e0e0;box-shadow:0 2px 4px rgba(0,0,0,0.08);"
    return f'''<td style="text-align:center;padding:6px 10px;vertical-align:top;width:56px;">
        <div style="width:38px;height:38px;border-radius:50%;
                    background-color:{hex_val};{shadow}
                    margin:0 auto 4px;"></div>
        <div style="font-size:10px;color:#888;">{name}</div>
    </td>'''


def generate_html(data, xhs_notes):
    """生成完整HTML推送内容 - 极简风格，只展示大吉+次吉"""

    # 提取大吉色和次吉色数据
    daji_data = data["colors"]["daji"]
    ciji_data = data["colors"]["ciji"]

    daji_colors = daji_data.get("colors", [])
    ciji_colors = ciji_data.get("colors", [])
    daji_yuyi = daji_data.get("yuyi", "")

    # 主色 = 大吉色第一个颜色
    main_color_name = daji_colors[0] if daji_colors else "未知"
    main_hex = COLOR_MAP.get(main_color_name, "#cccccc")

    # 浅色主色需要边框和阴影
    light_main = main_hex in ("#ffffff", "#f5f5dc", "#c0c0c0")
    main_shadow = ("border:1px solid #e0e0e0;"
                   "box-shadow:0 4px 20px rgba(0,0,0,0.1),"
                   "inset 0 0 0 3px #fff;") if light_main else \
                  ("box-shadow:0 4px 20px rgba(0,0,0,0.25),"
                   "inset 0 0 0 3px rgba(255,255,255,0.2);")

    # 备选色 = 大吉剩余 + 次吉全部，分两行排列（每行最多5个）
    match_colors = daji_colors[1:] + ciji_colors
    per_row = 5
    row1 = match_colors[:per_row]
    row2 = match_colors[per_row:per_row * 2]

    row1_html = "".join(small_color_dot(c) for c in row1)
    row2_html = "".join(small_color_dot(c) for c in row2) if row2 else ""

    match_table = f'''<table style="width:100%;border-collapse:collapse;margin:0 auto;">
            <tr>{row1_html}</tr>
            {f'<tr>{row2_html}</tr>' if row2_html else ''}
        </table>'''

    # 星期几
    weekdays = ["日", "一", "二", "三", "四", "五", "六"]
    tomorrow = datetime.now(BJT) + timedelta(days=1)
    weekday = weekdays[tomorrow.weekday()]

    # 干支信息
    gz = data.get("ganzhi", {})
    gz_day = gz.get("干支日柱", "")
    gz_wuxing = gz.get("日干五行", "")
    gz_text = f"{gz_day}日 · 五行{gz_wuxing}" if gz_day else ""

    # 穿搭建议文案（已移除，不再显示）

    html = f'''<div style="font-family:-apple-system,'PingFang SC','Helvetica Neue',sans-serif;
                max-width:380px;margin:0 auto;padding:16px;background-color:#fff;">
        <!-- 顶部渐变区 -->
        <div style="background:linear-gradient(135deg,#667eea,#764ba2,#a855f7);
                    border-radius:18px 18px 18px 18px;padding:28px 20px 24px;
                    text-align:center;color:#fff;">
            <!-- 标签 -->
            <div style="font-size:11px;letter-spacing:5px;opacity:0.75;margin-bottom:10px;">TOMORROW</div>
            <!-- 日期 -->
            <div style="font-size:26px;font-weight:bold;margin-bottom:4px;letter-spacing:1px;">
                {tomorrow.year}年{str(tomorrow.month).zfill(2)}月{str(tomorrow.day).zfill(2)}日
            </div>
            <!-- 副标题 -->
            <div style="font-size:13px;opacity:0.85;margin-top:6px;">
                ✨ 明日幸运色指南
            </div>
        </div>

        <!-- 主色大圆 -->
        <div style="text-align:center;padding:28px 0 16px;">
            <!-- 圆形色块 -->
            <div style="width:100px;height:100px;border-radius:50%;
                        background-color:{main_hex};{main_shadow}
                        margin:0 auto 16px;display:inline-block;"></div>
            <!-- 颜色名 -->
            <div style="font-size:26px;font-weight:bold;color:#222;margin-bottom:6px;">
                {main_color_name}
            </div>
            <!-- 标签 -->
            <div style="display:inline-block;font-size:12px;color:#aaa;background:#f5f5f5;
                        padding:3px 14px;border-radius:20px;letter-spacing:1px;">
                ● 明日大吉色
            </div>
        </div>

        <!-- 分隔线 -->
        <div style="width:30px;height:3px;background:linear-gradient(90deg,#667eea,#a855f7);
                    border-radius:2px;margin:22px auto;"></div>

        <!-- 备选颜色 -->
        <div style="padding:0 10px;margin-bottom:4px;">
            <div style="font-size:12px;color:#bbb;margin-bottom:10px;letter-spacing:1px;">
                ✦ 备选颜色
            </div>
            {match_table}
        </div>

        <!-- 底部 -->
        <div style="text-align:center;padding:20px 0 4px;font-size:10px;color:#ccc;letter-spacing:0.5px;">
            数据来源：{data.get('source', '综合')} · {gz_text}<br/>
            每日 21:00 自动推送
        </div>
    </div>'''

    return html


# ===== 推送 =====

def push_message(token, title, content):
    """调用PushPlus API推送消息到微信"""
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html",
    }
    headers = {"Content-Type": "application/json"}

    resp = requests.post(PUSHPLUS_API, json=payload, headers=headers, timeout=30)
    result = resp.json()

    if result.get("code") == 200:
        print(f"[OK] 推送成功！流水号: {result.get('data')}")
        return result
    else:
        print(f"[FAIL] 推送失败: {result}")
        sys.exit(1)


# ===== 主函数 =====

def main():
    # 1. 获取 PushPlus Token
    token = os.environ.get("PUSHPLUS_TOKEN")
    if not token:
        print("[ERROR] 未设置 PUSHPLUS_TOKEN 环境变量")
        print("提示: 在GitHub Secrets中添加 PUSHPLUS_TOKEN，或本地运行时设置环境变量")
        sys.exit(1)

    # 2. 计算明天日期（北京时间）
    tomorrow = datetime.now(BJT) + timedelta(days=1)
    date_str = f"{tomorrow.year}-{tomorrow.month}-{tomorrow.day}"
    title = f"{tomorrow.month}月{tomorrow.day}日幸运色指南"

    # 3. 爬取五行穿衣数据（多数据源自动容错）
    print(f"[INFO] 正在获取明天({date_str})的五行穿衣数据...")
    try:
        data = fetch_wuxing_data(date_str)
        print(f"[OK] 数据获取成功，来源: {data.get('source', '未知')}")
    except Exception as e:
        print(f"[FAIL] 所有数据源均获取失败: {e}")
        sys.exit(1)

    # 4. 生成HTML推送内容
    html_content = generate_html(data, [])
    print("[OK] HTML内容生成完成")

    # 5. 推送到微信
    print(f"[INFO] 正在推送到微信，标题: {title}")
    push_message(token, title, html_content)


if __name__ == "__main__":
    main()
