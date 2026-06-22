# -*- coding: utf-8 -*-
"""
每日幸运色微信推送脚本
- 主数据源：问运势网五行穿衣指南
- 补充数据源：小红书搜索（容错，失败不影响推送）
- 推送渠道：PushPlus → 微信
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone
from bs4 import BeautifulSoup

# ===== 常量 =====

PUSHPLUS_API = "http://www.pushplus.plus/send"
BJT = timezone(timedelta(hours=8))

# 颜色名称 → CSS 颜色值映射
COLOR_MAP = {
    "黑色": "#000000",
    "蓝色": "#0066cc",
    "白色": "#ffffff",
    "银色": "#c0c0c0",
    "米白": "#f5f5dc",
    "灰色": "#808080",
    "红色": "#dc3545",
    "紫色": "#6f42c1",
    "粉色": "#e83e8c",
    "橙红": "#ff6347",
    "绿色": "#28a745",
    "青色": "#17a2b8",
    "青绿": "#20c997",
    "翠绿": "#00d084",
    "黄色": "#ffc107",
    "咖色": "#8b4513",
    "棕色": "#a0522d",
    "褐色": "#800000",
    "橙黄": "#fd7e14",
}

# 颜色等级配置
LEVEL_CONFIG = {
    "daji":     {"label": "大吉 · 贵人色", "gradient": "linear-gradient(135deg,#2d8f4e,#1b5e20)", "accent": "#2d8f4e", "icon": "✦"},
    "ciji":     {"label": "次吉 · 合作色", "gradient": "linear-gradient(135deg,#0097a7,#006064)", "accent": "#0097a7", "icon": "◇"},
    "pingping": {"label": "平平 · 招财色", "gradient": "linear-gradient(135deg,#c99700,#8b6914)", "accent": "#c99700", "icon": "○"},
    "shenyong": {"label": "慎用 · 消耗色", "gradient": "linear-gradient(135deg,#e65100,#bf360c)", "accent": "#e65100", "icon": "△"},
    "jiyong":   {"label": "忌用 · 不利色", "gradient": "linear-gradient(135deg,#c62828,#8e0000)", "accent": "#c62828", "icon": "✕"},
}


# ===== 数据爬取 =====

def fetch_wuxing_data(date_str):
    """爬取并解析五行穿衣网站数据"""
    url = f"https://www.wenyunshi.com/sm/wuxingchuanyi/{date_str}.html"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.wenyunshi.com/sm/wuxingchuanyi/",
    }

    resp = requests.get(url, headers=headers, timeout=15)
    resp.encoding = "utf-8"

    if resp.status_code != 200:
        raise Exception(f"五行穿衣网站请求失败，状态码: {resp.status_code}")

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
            colors[class_name] = {
                "label": config["label"],
                "effect": "",
                "colors": [],
                "summary": "",
                "yuyi": "",
                "jieshi": "",
            }
            continue

        # 颜色名称列表
        color_names = [cn.get_text(strip=True) for cn in block.select(".color-name")]

        # 效果文字
        effect_el = block.select_one(".recommend-effect")
        effect = effect_el.get_text(strip=True) if effect_el else ""

        # 颜色汇总
        summary_el = block.select_one(".color-summary")
        summary = summary_el.get_text(strip=True) if summary_el else ""

        # 寓意和解释
        yuyi_el = block.select_one(".yuyi-text")
        jieshi_el = block.select_one(".jieshi-text")
        yuyi = yuyi_el.get_text(strip=True) if yuyi_el else ""
        jieshi = jieshi_el.get_text(strip=True) if jieshi_el else ""

        colors[class_name] = {
            "label": config["label"],
            "effect": effect,
            "colors": color_names,
            "summary": summary,
            "yuyi": yuyi,
            "jieshi": jieshi,
        }
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

    return data


def search_xiaohongshu():
    """尝试搜索小红书，失败返回空列表（不影响主流程）"""
    try:
        keywords = ["明日幸运色穿搭", "今日穿搭幸运色"]
        results = []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }

        # 尝试访问小红书搜索页面（反爬严格，很可能失败）
        url = "https://www.xiaohongshu.com/search_result"
        params = {"keyword": keywords[0], "source": "web_search_result_notes"}
        resp = requests.get(url, headers=headers, params=params, timeout=10)

        if resp.status_code != 200:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        # 尝试提取搜索结果中的笔记标题
        for note in soup.select(".note-item"):
            title_el = note.select_one(".title")
            if title_el:
                title = title_el.get_text(strip=True)
                if any(kw in title for kw in ["幸运色", "穿搭", "颜色", "五行穿衣", "旺运"]):
                    results.append({"title": title, "desc": ""})

        return results[:3]  #最多取3条

    except Exception as e:
        print(f"[WARN] 小红书搜索失败(不影响推送): {e}")
        return []


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
    gz_text = f"{gz.get('干支年柱', '')}年 {gz.get('干支月柱', '')}月 {gz.get('干支日柱', '')}日 · 五行{gz.get('日干五行', '')}"

    # 穿搭建议文案
    tip_text = daji_yuyi or data["colors"]["daji"].get("effect", "")
    suggestion_html = ""
    if tip_text:
        suggestion_html = f'''
        <div style="background-color:#fafafa;border-radius:14px;padding:16px 18px;
                    margin-top:24px;border-left:3px solid #7c7ce0;">
            <div style="font-size:13px;color:#666;line-height:1.9;">
                <span style="color:#999;margin-right:4px;">💡</span>{tip_text}
            </div>
        </div>'''

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

        <!-- 搭配推荐 -->
        <div style="padding:0 10px;margin-bottom:4px;">
            <div style="font-size:12px;color:#bbb;margin-bottom:10px;letter-spacing:1px;">
                ✦ 备选颜色
            </div>
            {match_table}
        </div>

        {suggestion_html}

        <!-- 底部 -->
        <div style="text-align:center;padding:20px 0 4px;font-size:10px;color:#ccc;letter-spacing:0.5px;">
            数据来源：问运势网 · {gz_text}<br/>
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

    # 3. 爬取五行穿衣数据
    print(f"[INFO] 正在获取明天({date_str})的五行穿衣数据...")
    try:
        data = fetch_wuxing_data(date_str)
        print(f"[OK] 数据获取成功: {data['solar_date']}")
    except Exception as e:
        print(f"[FAIL] 五行穿衣数据获取失败: {e}")
        sys.exit(1)

    # 4. 尝试搜索小红书（容错）
    print("[INFO] 尝试搜索小红书补充数据...")
    xhs_notes = search_xiaohongshu()
    if xhs_notes:
        print(f"[OK] 小红书获取到 {len(xhs_notes)} 条建议")
    else:
        print("[INFO] 小红书搜索无结果(不影响推送)")

    # 5. 生成HTML推送内容
    html_content = generate_html(data, xhs_notes)
    print("[OK] HTML内容生成完成")

    # 6. 推送到微信
    print(f"[INFO] 正在推送到微信，标题: {title}")
    push_message(token, title, html_content)


if __name__ == "__main__":
    main()
