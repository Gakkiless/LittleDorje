#!/usr/bin/env python3
"""
松赞产品推荐助手 - 后端API服务
提供推荐算法接口，支持微信小程序调用
"""
import sys
import time
import json
import re
import requests
from pathlib import Path
from typing import Optional
from flask import Flask, request, jsonify
from flask_cors import CORS

# 尝试导入可选依赖
try:
    import chromadb
    import ollama
    HAS_VECTOR_DB = True
except ImportError:
    HAS_VECTOR_DB = False

# ============ 配置 ============
TOKEN_FILE = Path(__file__).parent / ".token"
TOKEN_EXPIRY = 30 * 60  # token有效期（秒）
TOKEN_URL = "https://i.songtsam.com/uc-web/v2/password/loginSSO"
LOGIN_PAYLOAD = {
    "orgCode": "SONGTSAM",
    "userCode": "13678767674",
    "password": "L+THB3NojO1oYnHv2u6D/QdwZQQqCQYWtM8DCXBerm5A6y32zcNgf2ojbGsjun6vhiKfYrUuvNrrFlehIkJJSVrO6k3jHzZrVyohtfnD8mVdDOe//bhelrR5DURe+L+1iJxe+DtATNasuGpYePz6mh0WlkuycuIdEhqSsPL0GP/xUrHWC+pYxygsIie0tcV2UK79aniKd4kggloOn6IkFytEKqOc2RjmWFUFR243rxeN6trKv9DKfCtOJ7LxKvbnCKNwhJ73p3jrbI18En26xiqXl9Dsj/B0yfCCxLcYbPMmzcLcxAbYISqCKQGYdeLgSGKlyXg3A/P8kmwtBAx23Q=="
}
HEADERS = {"Content-Type": "application/json"}
CHROMA_PATH = Path(__file__).parent / "chroma_db"
APP_PORT = 5123
ITINERARY_API = "https://gds.songtsam.com/product-journey/bks/itinerary/getTravelProductitinerary"
GROUP_API = "https://gds.songtsam.com/product-journey/bks/travelGroupProvider/listTravelGroupForOrder"
PRODUCT_API = "https://gds.songtsam.com/product-journey/bks/travelproduct/getTravelProductType"

# ============ 成本接口配置 ============
COST_APIS = {
    "profit": "https://api.songtsam.com/quotation_center/bks/profitItemManage/pageQuery",
    "hotel_calendar": "https://api.songtsam.com/quotation_center/bks/hotelCalendar/pageQuery",
    "hotel_cost": "https://api.songtsam.com/quotation_center/bks/hotelCostMeal/queryList",
    "external_dining": "https://api.songtsam.com/quotation_center/bks/externalDining/pageQuery",
    "activity_cost": "https://api.songtsam.com/quotation_center/bks/activityCost/pageQuery",
    "vehicle_cost": "https://api.songtsam.com/quotation_center/bks/vehicleCost/pageQuery",
    "other_cost": "https://api.songtsam.com/quotation_center/bks/otherCostItem/pageQuery",
}

# 缓存
_cost_cache = {
    "profit": {"data": None, "time": 0},
    "hotel_calendar": {"data": None, "time": 0},
    "hotel_cost": {"data": None, "time": 0},
    "external_dining": {"data": None, "time": 0},
    "activity_cost": {"data": None, "time": 0},
    "vehicle_cost": {"data": None, "time": 0},
    "other_cost": {"data": None, "time": 0},
}
CACHE_TTL = 3600  # 缓存1小时

# ============ Flask App ============
app = Flask(__name__)
CORS(app)  # 允许跨域，支持小程序调用


# ============ Token管理 ============
def get_token():
    """获取/刷新 Token"""
    try:
        if TOKEN_FILE.exists():
            content = TOKEN_FILE.read_text().strip()
            # 兼容旧格式（纯 token 字符串）
            try:
                data = json.loads(content)
                if data.get("token") and time.time() - data.get("fetch_time", 0) < TOKEN_EXPIRY:
                    return data["token"]
            except json.JSONDecodeError:
                # 旧格式：直接是 token 字符串
                mtime = TOKEN_FILE.stat().st_mtime
                if time.time() - mtime < TOKEN_EXPIRY:
                    return content
    except:
        pass

    # 重新登录
    resp = requests.post(TOKEN_URL, json=LOGIN_PAYLOAD, headers=HEADERS, timeout=10)
    result = resp.json()
    token = result.get("retVal", {}).get("jwtToken") or result.get("retVal", {}).get("token")
    if token:
        TOKEN_FILE.write_text(json.dumps({"token": token, "fetch_time": time.time()}))
        return token
    return None


def get_auth_headers():
    """获取带认证的请求头"""
    token = get_token()
    if token:
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }
    return {"Content-Type": "application/json"}


def api_post(url, data, token=None):
    """POST 请求（带认证）"""
    if not token:
        token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=data, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ============ 成本接口 ============
def fetch_cost_data(api_key: str) -> dict:
    """获取成本数据，支持缓存"""
    now = time.time()
    cached = _cost_cache.get(api_key)

    # 检查缓存
    if cached and cached["data"] and (now - cached["time"]) < CACHE_TTL:
        return cached["data"]

    try:
        url = COST_APIS.get(api_key)
        if not url:
            return {}

        payload = {"hotelGroupCode": "SONGTSAM"}
        resp = requests.post(url, json=payload, headers=get_auth_headers(), timeout=10)
        result = resp.json()

        if result.get("retVal"):
            _cost_cache[api_key] = {"data": result["retVal"], "time": now}
            return result["retVal"]
    except Exception as e:
        print(f"[ERROR] 获取成本数据失败: {api_key}, {e}")

    return {}


def get_profit_config() -> dict:
    """获取利润率配置"""
    data = fetch_cost_data("profit")
    if isinstance(data, list):
        config = {}
        for item in data:
            name = item.get("itemName", "")
            value = item.get("itemValue", 0)
            if "节日" in name:
                config["节日"] = value
            elif "旺季" in name:
                config["旺季"] = value
            elif "平季" in name:
                config["平季"] = value
            elif "淡季" in name:
                config["淡季"] = value
        return config
    return {"节日": -5, "旺季": -2.5, "平季": 0, "淡季": 5}


def get_season(date_str: str) -> str:
    """根据日期判断季节"""
    try:
        month = int(date_str.split("-")[1]) if "-" in date_str else 1
        if month in [1, 2, 3, 4, 5, 10, 11, 12]:
            return "淡季"
        elif month in [6, 7, 8, 9]:
            return "旺季"
    except:
        pass
    return "平季"


def calculate_package_price(
    hotel_cost: float,
    vehicle_cost: float,
    driver_cost: float,
    escort_cost: float,  # 管家/导游
    dining_cost: float,
    activity_cost: float,
    insurance: float,
    other_cost: float,
    date_str: str,
    is_custom: bool = False
) -> dict:
    """计算打包价

    公式: 打包价 = 元素总成本 / 成本率
    成本率 = 1 - 利润率
    利润率 = 集团分摊10% + 基础成本率5% - 季节成本率
    """
    # 集团分摊与息税率（固定10%）
    GROUP_TAX = 10
    # 基础成本率（固定5%）
    BASE_COST = 5
    # 季节成本率
    season = get_season(date_str)
    profit_config = get_profit_config()
    season_rate = profit_config.get(season, 0)

    # 利润率 = 集团分摊10% + 基础成本率5% - 季节成本率
    profit_rate = GROUP_TAX + BASE_COST - season_rate

    # 成本率 = 1 - 利润率
    cost_rate = 1 - (profit_rate / 100)

    # 元素总成本
    total_cost = (
        hotel_cost +
        vehicle_cost +
        driver_cost +
        escort_cost +
        dining_cost +
        activity_cost +
        insurance +
        other_cost
    )

    # 打包价 = 总成本 / 成本率
    package_price = total_cost / cost_rate if cost_rate > 0 else total_cost

    # 定制服务费
    custom_fee = package_price * 0.1 if is_custom else 0

    return {
        "total_cost": round(total_cost, 2),
        "package_price": round(package_price, 2),
        "custom_fee": round(custom_fee, 2),
        "final_price": round(package_price + custom_fee, 2),
        "profit_rate": profit_rate,
        "cost_rate": round(cost_rate * 100, 2),
        "season": season,
        "season_rate": season_rate,
        "breakdown": {
            "hotel": round(hotel_cost, 2),
            "vehicle": round(vehicle_cost, 2),
            "driver": round(driver_cost, 2),
            "escort": round(escort_cost, 2),
            "dining": round(dining_cost, 2),
            "activity": round(activity_cost, 2),
            "insurance": round(insurance, 2),
            "other": round(other_cost, 2),
        }
    }


# ============ 向量库功能 ============
def get_embedding(text: str):
    """获取文本embedding"""
    response = ollama.embeddings(model="nomic-embed-text", prompt=text)
    return response["embedding"]


def query_vectorstore(query_text: str, n_results: int = 50) -> list:
    """查询向量库"""
    client = chromadb.PersistentClient(path=str(CHROMA_PATH))
    collection = client.get_collection("songtsam_products")
    embedding = get_embedding(query_text)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results
    )
    products = []
    for i in range(len(results["ids"][0])):
        products.append({
            "id": results["ids"][0][i],
            "metadata": results["metadatas"][0][i],
            "document": results["documents"][0][i],
            "distance": results["distances"][0][i] if results.get("distances") else 0,
        })
    return products


# ============ 需求解析 ============
def parse_requirements(query: str) -> dict:
    req = {
        "days": None, "people": None, "budget": None, "type": None,
        "season": None, "location": None, "tag": None,
        "trip_type": None,  # 出行类型：情侣/家庭/闺蜜/银发/其他
        "with_elder_kids": False,  # 是否带老人小孩
        "is_foreigner": False,  # 是否有外籍
        "member_level": None,  # 会员等级
    }

    # === 出行类型识别 ===
    trip_type_keywords = {
        "情侣": ["情侣", "情侣游", "蜜月", "夫妻", "二人世界"],
        "家庭": ["家庭", "全家", "一家", "带爸妈", "带父母"],
        "闺蜜": ["闺蜜", "姐妹", "朋友", "结伴"],
        "银发": ["银发", "老人", "老年人", "父母", "长辈"],
    }
    for ttype, keywords in trip_type_keywords.items():
        if any(kw in query for kw in keywords):
            req["trip_type"] = ttype
            break

    # === 是否带老人小孩 ===
    if any(kw in query for kw in ["带小孩", "带小朋友", "带孩子", "亲子", "全家", "带爸妈", "带父母", "老人"]):
        req["with_elder_kids"] = True

    # === 是否外籍 ===
    if any(kw in query for kw in ["外籍", "外国人", "老外"]):
        req["is_foreigner"] = True

    # === 会员等级 ===
    member_map = {
        "格桑": 1.0,
        "绿绒蒿": 0.95,
        "雪莲": 0.9,
        "莲": 0.85,
        "金刚": 0.85,
    }
    for level, discount in member_map.items():
        if level in query:
            req["member_level"] = {"name": level, "discount": discount}
            break

    # 天数
    day_match = re.search(r"(\d+)\s*[天日]|[天日](\d+)", query)
    if day_match:
        for g in day_match.groups():
            if g and g.isdigit():
                req["days"] = int(g)
                break

    # 人数（情侣=2人，家庭按实际或默认4人）
    people_match = re.search(r"(\d+)\s*[人大客位]", query)
    if people_match:
        req["people"] = int(people_match.group(1))
    elif req["trip_type"] == "情侣":
        req["people"] = 2  # 情侣默认2人

    # 产品类型
    if any(kw in query for kw in ["自由行"]):
        req["type"] = "自由行"
    elif any(kw in query for kw in ["私享管家", "私享"]):
        req["type"] = "私享管家"
    elif any(kw in query for kw in ["主题团"]):
        req["type"] = "主题团"

    # 季节/主题
    if any(kw in query for kw in ["桃花", "桃花节"]):
        req["season"] = "桃花季"
    elif any(kw in query for kw in ["杜鹃", "杜鹃花", "杜鹃季"]):
        req["season"] = "杜鹃季"
    elif any(kw in query for kw in ["亲子", "小朋友", "小孩", "带小孩"]):
        req["season"] = "亲子"
    elif any(kw in query for kw in ["夏季", "夏天", "避暑"]):
        req["season"] = "夏季"

    # 目的地
    locations = {
        "拉萨": ["拉萨", "布达拉"],
        "林芝": ["林芝", "南迦巴瓦", "巴松措"],
        "波密": ["波密", "来古"],
        "梅里": ["梅里", "德钦"],
        "香格里拉": ["香格里拉", "奔子栏", "塔城"],
        "普洱": ["普洱"],
        "丽江": ["丽江"],
    }
    for loc, keywords in locations.items():
        if any(kw in query for kw in keywords):
            req["location"] = loc
            break

    # 标签匹配
    tag_map = {
        "主题团": ["主题团"],
        "私享管家": ["私享管家"],
        "自由行": ["自由行"],
        "亲子度假": ["亲子度假"],
        "亲子研学": ["亲子研学"],
        "深度户外": ["深度户外", "徒步", "穿越"],
        "轻户外": ["轻户外", "徒步"],
        "深度文化体验": ["深度文化体验", "文化"],
        "自然景观": ["自然景观", "风景"],
        "低空旅行": ["低空旅行", "直升机", "低空"],
        "高原花季": ["高原花季", "花季", "赏花"],
        "美食美酒": ["美食美酒", "美食", "美酒", "品酒"],
        "度假休闲": ["度假休闲", "度假", "休闲"],
        "疗愈": ["疗愈", "放松", "康养"],
        "自然博物": ["自然博物", "博物", "自然教育"],
        "摄影爱好": ["摄影爱好", "摄影"],
        "低海拔": ["低海拔"],
        "银发出行": ["银发出行"],
        "寻找珍贵风物": ["寻找珍贵风物", "风物", "物产"],
        "目的地套餐": ["目的地套餐", "套餐"],
    }
    for tag, keywords in tag_map.items():
        if any(kw in query for kw in keywords):
            req["tag"] = tag
            break

    # 如果识别到出行类型但没匹配到对应标签，自动设置
    if req["trip_type"] == "银发" and not req["tag"]:
        req["tag"] = "低海拔"
    if req["trip_type"] == "家庭" and not req["season"]:
        req["season"] = "亲子"

    return req


# ============ 产品形态权重配置 ============
PRODUCT_TYPE_WEIGHTS = {
    "私享管家": {
        "default": 0.8,
        "by_people": {
            (1, 1): 0.2,
            (2, 2): 1.5,
            (3, 4): 1.2,
            (5, 999): 0.5,
        }
    },
    "主题团": {
        "default": 0.8,
        "by_people": {
            (1, 1): 1.5,
            (2, 2): 1.0,
            (3, 4): 1.0,
            (5, 999): 1.5,
        }
    },
    "自由行": {
        "default": 0.5,
        "by_people": {
            (1, 1): 0.3,
            (2, 2): 0.8,
            (3, 999): 0.2,
        }
    },
}


def get_product_type_weight(product_type: str, people: int) -> tuple:
    """根据人数获取产品形态权重，返回 (weight, desc)"""
    if not product_type:
        return 0, ""
    cfg = PRODUCT_TYPE_WEIGHTS.get(product_type, {"default": 0, "by_people": {}})
    for (low, high), weight in cfg.get("by_people", {}).items():
        if low <= people <= high:
            desc_map = {
                "私享管家": {
                    (1, 1): "私密小团，管家服务",
                    (2, 2): "2人私密小团，管家全程服务",
                    (3, 4): "小团出行，管家服务更贴心",
                    (5, 999): "可包团，管家专属服务",
                },
                "主题团": {
                    (1, 1): "1人可拼团，和陌生人拼房免单房差",
                    (2, 2): "2人可拼团，性价比高",
                    (3, 4): "3-4人拼团（4人需看是否有标品变形）",
                    (5, 999): "拼团最划算",
                },
                "自由行": {
                    (1, 1): "不含管家，需解决单房差",
                    (2, 2): "不含管家，自由自驾",
                    (3, 999): "不含管家，需自驾",
                },
            }
            desc = desc_map.get(product_type, {}).get((low, high), "")
            return weight, desc
    return cfg.get("default", 0), ""


# ============ 评分逻辑 ============
def score_product(product: dict, req: dict) -> float:
    meta = product.get("metadata", {})
    score = 1.0
    reasons = []

    # === 1. 天数匹配 ===
    if req.get("days") and meta.get("itinerary_days"):
        diff = abs(req["days"] - meta.get("itinerary_days", 0))
        if diff == 0:
            score += 0.5
            reasons.append("天数完全匹配")
        elif diff <= 1:
            score += 0.2
            reasons.append("天数相近")

    # === 2. 产品形态×人数 适配 ===
    people = req.get("people") or 0
    product_tags = meta.get("tags", "")
    category_sub = meta.get("category_sub", "")

    supported_types = []
    for ptype in ["私享管家", "主题团", "自由行"]:
        if ptype in product_tags or ptype in category_sub:
            supported_types.append(ptype)

    if people > 0 and supported_types:
        primary_type = supported_types[0]
        weight, desc = get_product_type_weight(primary_type, people)
        if weight > 0:
            score += weight
            if desc:
                reasons.append(f"[{primary_type}] {desc}")
        if len(supported_types) > 1:
            type_names = "+".join(supported_types)
            reasons.append(f"可选形态: {type_names}")
    elif req.get("type"):
        if req["type"] in product_tags or req["type"] in category_sub:
            score += 0.5
            reasons.append(f"产品类型: {req['type']}")

    # === 3. 季节/主题匹配 ===
    if req.get("season"):
        tags = meta.get("tags", "")
        title = meta.get("title", "")
        season_match = False
        if req["season"] == "桃花季" and ("桃花季" in tags or "桃花季" in title):
            season_match = True
        elif req["season"] == "杜鹃季" and "杜鹃季" in title:
            season_match = True
        elif req["season"] in tags:
            season_match = True
        if season_match:
            score += 0.5
            reasons.append(f"符合{req['season']}主题")

    # === 4. 目的地匹配 ===
    if req.get("location"):
        title = meta.get("title", "")
        series = meta.get("series", "")
        if req["location"] in title or req["location"] in series:
            score += 0.4
            reasons.append(f"目的地在{req['location']}")

    # === 5. 标签匹配 ===
    if req.get("tag"):
        if req["tag"] in meta.get("tags", ""):
            score += 1.0
            reasons.append(f"标签匹配: {req['tag']}")

    # === 6. 出行类型匹配 ===
    trip_type = req.get("trip_type")
    if trip_type:
        product_tags_str = meta.get("tags", "")
        if trip_type == "情侣":
            if "私享管家" in product_tags_str or "私享管家" in category_sub:
                score += 1.2
                reasons.append("💑 情侣首选：私密小团，浪漫专属")
            elif "自由行" in product_tags_str:
                score += 0.6
                reasons.append("💑 情侣可选：自由浪漫")
            if "主题团" in supported_types and len(supported_types) == 1:
                score -= 0.5
        elif trip_type == "家庭":
            if any(t in product_tags_str for t in ["亲子度假", "亲子研学", "亲子"]):
                score += 1.5
                reasons.append("👨‍👩‍👧‍👦 家庭首选：亲子产品")
            elif "私享管家" in product_tags_str:
                score += 0.8
                reasons.append("👨‍👩‍👧‍👦 家庭可选：管家服务贴心")
        elif trip_type == "银发":
            if any(t in product_tags_str for t in ["低海拔", "度假休闲", "疗愈"]):
                score += 1.5
                reasons.append("👴👵 银发首选：低海拔/轻松休闲")
            elif "轻户外" in product_tags_str:
                score += 0.8
                reasons.append("👴👵 银发可选：轻户外体验")
            if "深度户外" in product_tags_str:
                score -= 0.8
                reasons.append("⚠️ 深度户外强度较大，需评估身体状况")
        elif trip_type == "闺蜜":
            if any(t in product_tags_str for t in ["轻户外", "美食美酒", "摄影爱好", "度假休闲"]):
                score += 1.2
                reasons.append("👭 闺蜜推荐：拍照美食两不误")

    # === 7. 外籍提醒 ===
    if req.get("is_foreigner"):
        title = meta.get("title", "")
        if "西藏" in title or "拉萨" in title or "林芝" in title:
            reasons.append("⚠️ 注意：西藏行程需入藏函，请提前确认")

    product["score"] = score
    product["reasons"] = reasons
    return score


# ============ 展示策略 ============
def get_display_strategy(people: int, user_type: str = None, trip_type: str = None) -> dict:
    """根据人数和出行类型决定推荐展示策略"""
    if user_type:
        return {
            "mode": "single",
            "show_types": [user_type],
            "sort_priority": [user_type],
            "tip": f"为您筛选【{user_type}】产品"
        }

    if trip_type == "情侣":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "自由行", "主题团"],
            "sort_priority": ["私享管家", "自由行", "主题团"],
            "tip": "💑 情侣出行推荐【私享管家】，私密浪漫管家专属服务 ↓"
        }
    if trip_type == "家庭":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团"],
            "sort_priority": ["私享管家", "主题团"],
            "tip": "👨‍👩‍👧‍👦 家庭出行推荐【私享管家】，管家照顾老小更贴心 ↓"
        }
    if trip_type == "银发":
        return {
            "mode": "single",
            "show_types": ["私享管家"],
            "sort_priority": ["私享管家"],
            "tip": "👴👵 银发出行推荐【私享管家】，节奏灵活可根据身体状况调整"
        }
    if trip_type == "闺蜜":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "自由行"],
            "sort_priority": ["私享管家", "自由行"],
            "tip": "👭 闺蜜出行推荐【私享管家】或【自由行】，轻松自由 ↓"
        }

    if not people:
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团", "自由行"],
            "sort_priority": ["私享管家", "主题团", "自由行"],
            "tip": "以下3种玩法各有特色，您可以选择适合您的"
        }
    if people == 1:
        return {
            "mode": "single",
            "show_types": ["主题团"],
            "sort_priority": ["主题团"],
            "tip": "1人出行推荐【主题团】，可拼团和陌生人拼房免单房差"
        }
    if people == 2:
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团", "自由行"],
            "sort_priority": ["私享管家", "主题团", "自由行"],
            "tip": "2人出行有3种玩法可选，各有特色 ↓"
        }
    if people == 3:
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团"],
            "sort_priority": ["主题团", "私享管家"],
            "tip": "3人推荐【主题团】（拼团划算）或【私享管家】↓"
        }
    if people == 4:
        return {
            "mode": "single",
            "show_types": ["主题团"],
            "sort_priority": ["主题团"],
            "tip": "4人通常为标品变形，可选主题团（需确认团期）"
        }
    return {
        "mode": "single",
        "show_types": ["主题团"],
        "sort_priority": ["主题团"],
        "tip": f"{people}人【主题团】最划算，8-12人标准规模拼团分摊成本"
    }


# ============ 团期查询 ============
def query_groups(travel_type: str, token: str, max_groups: int = 3, preferred_month: str = None) -> list:
    """查询产品的可预订团期"""
    try:
        all_groups = []
        for page in [0, 100]:
            data = api_post(
                f"{GROUP_API}?firstResult={page}&pageSize=100&unitCode=SONGTSAM",
                {"travelType": travel_type},
                token=token
            )
            groups = data.get("retVal", {}).get("datas", [])
            if isinstance(groups, list):
                all_groups.extend(groups)

        seen = set()
        unique_groups = []
        for g in all_groups:
            code = g.get("travelGroupCode", "")
            if code and code not in seen:
                seen.add(code)
                unique_groups.append(g)

        available = [g for g in unique_groups if g.get("saleNum", 0) > 0]
        available.sort(key=lambda x: x.get("groupBeginDate", ""))

        if preferred_month:
            month_groups = [g for g in available if g.get("groupBeginDate", "").startswith(preferred_month)]
            if month_groups:
                return month_groups[:max_groups]

        return available[:max_groups]
    except Exception as e:
        return []


# ============ API 路由 ============
@app.route("/api/recommend", methods=["POST"])
def recommend():
    """
    推荐接口
    请求: {"query": "2人情侣去林芝看桃花", "preferred_month": "2026-05"}
    返回: {"success": true, "data": {...}}
    """
    try:
        data = request.get_json()
        query = data.get("query", "")
        preferred_month = data.get("preferred_month", None)

        if not query:
            return jsonify({"success": False, "error": "请输入您的需求"})

        # 解析需求
        req = parse_requirements(query)

        # 自动提取优先月份（如果未传入）
        if not preferred_month:
            m = re.search(r'(\d+)月', query)
            if m:
                month = int(m.group(1))
                preferred_month = f"2026-{month:02d}"

        strategy = get_display_strategy(req.get("people", 0), req.get("type"), req.get("trip_type"))

        # 向量搜索
        vector_results = []
        if HAS_VECTOR_DB:
            try:
                vector_results = query_vectorstore(query, n_results=100)
            except Exception as e:
                pass

        # 规则评分排序
        for p in vector_results:
            score_product(p, req)
        vector_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # 取前20个，查询团期
        top_products = vector_results[:20]
        token = get_token()
        for p in top_products:
            tid = p.get("metadata", {}).get("travel_type")
            if tid:
                p["groups"] = query_groups(tid, token, preferred_month=preferred_month)
            else:
                p["groups"] = []

        # 按形态分组
        by_type = {"私享管家": [], "主题团": [], "自由行": []}
        for p in top_products:
            meta = p.get("metadata", {})
            product_tags = meta.get("tags", "")
            category_sub = meta.get("category_sub", "")
            title = meta.get("title", "")
            season = req.get("season", "")

            supported = []
            for ptype in ["私享管家", "主题团", "自由行"]:
                if ptype in product_tags or ptype in category_sub:
                    supported.append(ptype)

            if not supported:
                continue

            p["supported_types"] = supported

            # 季节产品加入所有支持的形态
            is_season = (season == "杜鹃季" and "杜鹃季" in title) or \
                        (season == "桃花季" and ("桃花季" in title or "桃花季" in product_tags))
            if is_season:
                for ptype in supported:
                    by_type[ptype].append(p)
            else:
                by_type[supported[0]].append(p)

        # 构建返回数据
        products_by_type = {}
        for ptype in strategy.get("sort_priority", ["私享管家", "主题团", "自由行"]):
            type_products = by_type.get(ptype, [])
            # 有团期的优先
            type_products.sort(key=lambda x: (1 if x.get("groups") else 0, x.get("score", 0)), reverse=True)
            items = []
            for p in type_products[:3]:
                meta = p.get("metadata", {})
                groups = p.get("groups", [])
                items.append({
                    "id": p.get("id"),
                    "title": meta.get("title", ""),
                    "tags": meta.get("tags", ""),
                    "score": round(p.get("score", 0), 2),
                    "reasons": p.get("reasons", []),
                    "supported_types": p.get("supported_types", []),
                    "nights": meta.get("itinerary_nights"),
                    "days": meta.get("itinerary_days"),
                    "travel_type": meta.get("travel_type", ""),
                    "groups": [
                        {
                            "begin": g.get("groupBeginDate", "")[:10],
                            "price": g.get("startingPrice", 0),
                            "remaining": g.get("saleNum", 0),
                            "total": g.get("productNum", 0),
                            "code": g.get("travelGroupCode", ""),
                        }
                        for g in groups
                    ],
                })
            if items:
                products_by_type[ptype] = items

        result = {
            "success": True,
            "query": query,
            "requirements": req,
            "strategy": strategy,
            "products_by_type": products_by_type,
            "has_vector_db": HAS_VECTOR_DB,
        }

        return jsonify(result)

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()})


@app.route("/api/health", methods=["GET"])
def health():
    """健康检查"""
    return jsonify({
        "status": "ok",
        "has_vector_db": HAS_VECTOR_DB,
        "port": APP_PORT
    })


@app.route("/api/price", methods=["POST"])
def calculate_price():
    """计价接口
    请求: {
        "date": "2026-04-22",
        "hotel": {"code": "STNJBW", "nights": 2, "rooms": 1},
        "vehicle": {"type": "路虎卫士", "days": 3},
        "driver": {"days": 3, "price_per_day": 600},
        "escort": {"days": 3, "price_per_day": 800},
        "dining": {"breakfast": 150, "lunch": 200, "dinner": 250, "meals": 9},
        "activity": {"items": [{"name": "雅鲁藏布大峡谷", "price": 500}], "count": 1},
        "people": 2,
        "is_custom": false
    }
    """
    try:
        data = request.get_json()
        date_str = data.get("date", "")
        people = data.get("people", 2)
        is_custom = data.get("is_custom", False)

        # 酒店成本
        hotel_cost = data.get("hotel", {}).get("cost", 0)

        # 车辆成本
        vehicle_cost = data.get("vehicle", {}).get("cost", 0)

        # 司机成本
        driver = data.get("driver", {})
        driver_cost = driver.get("days", 0) * driver.get("price_per_day", 0)

        # 管家成本
        escort = data.get("escort", {})
        escort_cost = escort.get("days", 0) * escort.get("price_per_day", 0)

        # 餐饮成本
        dining = data.get("dining", {})
        dining_cost = dining.get("cost", 0)

        # 活动成本
        activity = data.get("activity", {})
        activity_cost = activity.get("cost", 0)

        # 保险（按人数）
        insurance = people * 50  # 假设每人50元保险

        # 其他成本
        other_cost = data.get("other_cost", 0)

        # 计算打包价
        result = calculate_package_price(
            hotel_cost=hotel_cost,
            vehicle_cost=vehicle_cost,
            driver_cost=driver_cost,
            escort_cost=escort_cost,
            dining_cost=dining_cost,
            activity_cost=activity_cost,
            insurance=insurance,
            other_cost=other_cost,
            date_str=date_str,
            is_custom=is_custom
        )

        # 添加成本明细
        result["cost_detail"] = {
            "hotel": {"cost": hotel_cost, "desc": "酒店住宿"},
            "vehicle": {"cost": vehicle_cost, "desc": "车辆"},
            "driver": {"cost": driver_cost, "desc": "司机"},
            "escort": {"cost": escort_cost, "desc": "管家/导游"},
            "dining": {"cost": dining_cost, "desc": "餐饮"},
            "activity": {"cost": activity_cost, "desc": "活动"},
            "insurance": {"cost": insurance, "desc": f"保险({people}人)"},
            "other": {"cost": other_cost, "desc": "其他"},
        }

        return jsonify({
            "success": True,
            "date": date_str,
            "people": people,
            "is_custom": is_custom,
            "pricing": result
        })

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/costs", methods=["GET"])
def get_costs():
    """获取各成本配置（用于调试）"""
    try:
        result = {}
        for key in COST_APIS:
            data = fetch_cost_data(key)
            result[key] = data
        return jsonify({"success": True, "costs": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route("/api/parse", methods=["POST"])
def parse():
    """仅解析需求，不返回推荐"""
    try:
        data = request.get_json()
        query = data.get("query", "")
        req = parse_requirements(query)
        strategy = get_display_strategy(req.get("people", 0), req.get("type"), req.get("trip_type"))
        return jsonify({"success": True, "requirements": req, "strategy": strategy})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ============ 启动 ============
if __name__ == "__main__":
    print(f"""
╔══════════════════════════════════════════════╗
║   小多吉推荐API服务                           ║
║   端口: {APP_PORT}                                  ║
║   向量库: {"已启用 ✓" if HAS_VECTOR_DB else "未安装 (pip install chromadb ollama)"}    ║
╚══════════════════════════════════════════════╝
    """)
    app.run(host="0.0.0.0", port=APP_PORT, debug=True)
