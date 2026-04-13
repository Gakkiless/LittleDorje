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

# ============ AI 模型配置 ============
# 智谱AI（GLM系列）- OpenAI 兼容协议
AI_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
AI_MODEL = "glm-4.5-air"   # 智谱 GLM-4.5-Air，快速版
AI_API_KEY = ""  # 从环境变量读取，见下方 get_ai_api_key()

def get_ai_api_key() -> str:
    """获取智谱 AI API Key（环境变量 > .token 文件）"""
    key = os.environ.get("ZHIPU_API_KEY")
    if key:
        return key
    token_file = Path(__file__).parent / ".token"
    if token_file.exists():
        for line in token_file.read_text().strip().splitlines():
            if line.startswith("ZHIPU_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


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


@app.route("/api/groups-direct", methods=["POST"])
def groups_direct():
    """
    直查团期接口（不走推荐算法）
    请求: {
        "keyword": "亚丁远山",       // 产品名关键词
        "month": "2026-05",         // 可选，优先月份
        "max_groups": 20            // 可选，最多返回几个团期，默认20
    }
    返回: {
        "success": true,
        "products": [
            {
                "travel_type": "ST-YDYYY-ZT",
                "title": "亚丁的远山...",
                "groups": [
                    {
                        "code": "ST-YDYYY-ZT-20260512",
                        "begin": "2026-05-12",
                        "end": "2026-05-18",
                        "price": 12800,
                        "remaining": 4,
                        "total": 12
                    }
                ]
            }
        ]
    }
    """
    try:
        body = request.get_json() or {}
        keyword = body.get("keyword", "").strip()
        month = body.get("month", None)
        max_groups = int(body.get("max_groups", 20))

        if not keyword:
            return jsonify({"success": False, "error": "请输入产品名关键词"})

        token = get_token()
        if not token:
            return jsonify({"success": False, "error": "Token获取失败，请检查账号配置"})

        # 先通过向量库查找匹配产品
        matched_products = []
        if HAS_VECTOR_DB:
            try:
                results = query_vectorstore(keyword, n_results=30)
                for p in results:
                    title = p.get("metadata", {}).get("title", "")
                    travel_type = p.get("metadata", {}).get("travel_type", "")

                    matched = False
                    # 策略1：精确完整匹配（关键词完整出现在标题中）
                    if keyword and keyword in title:
                        matched = True
                    # 策略2："｜"分隔，类别+品名均须出现在标题中
                    # "香格里拉环线｜亚丁的远山" → 标题必须含两者
                    elif '｜' in keyword:
                        parts = [k.strip() for k in keyword.split('｜') if k.strip()]
                        if parts and all(part in title for part in parts):
                            matched = True

                    if matched:
                        matched_products.append({
                            "travel_type": travel_type,
                            "title": title,
                            "tags": p.get("metadata", {}).get("tags", ""),
                            "nights": p.get("metadata", {}).get("itinerary_nights"),
                            "days": p.get("metadata", {}).get("itinerary_days"),
                        })

                # 去重（按 travel_type）
                seen = set()
                deduped = []
                for p in matched_products:
                    tt = p.get("travel_type", "")
                    if tt and tt not in seen:
                        seen.add(tt)
                        deduped.append(p)
                matched_products = deduped[:10]
            except Exception as e:
                print(f"[WARN] 向量库查询失败: {e}")

        # 如果向量库没结果，fallback：直接全量拉团期，按关键词精确过滤
        if not matched_products:
            try:
                all_groups = []
                for page in [0, 100, 200]:
                    data = api_post(
                        f"{GROUP_API}?firstResult={page}&pageSize=100&unitCode=SONGTSAM",
                        {},
                        token=token
                    )
                    groups = data.get("retVal", {}).get("datas", [])
                    if isinstance(groups, list):
                        all_groups.extend(groups)
                    else:
                        break

                # 关键词预处理：去掉末尾的 "X晚X天" 规格（因为 API 产品名的天数可能不同）
                import re
                kw_base = re.sub(r'\s*\d+晚\d+天\s*$', '', keyword).strip()

                # 精确过滤：keyword 或去掉天数后 均完整出现在 travelTypeDesc 中
                def keyword_match(ttd):
                    if keyword in ttd:
                        return True
                    if kw_base and kw_base in ttd:
                        return True
                    if '｜' in kw_base:
                        parts = [p.strip() for p in kw_base.split('｜') if p.strip()]
                        return parts and all(p in ttd for p in parts)
                    return False

                # 先按 travelType 去重，再过滤
                seen_tt = set()
                deduped = []
                for g in all_groups:
                    tt = g.get("travelType", "")
                    if tt and tt not in seen_tt:
                        seen_tt.add(tt)
                        deduped.append(g)

                # 精确匹配行程名称
                filtered = [g for g in deduped if keyword_match(g.get("travelTypeDesc", ""))]

                # 如果精确匹配为空，记录友好提示
                no_match_hint = ""
                if not filtered and kw_base:
                    no_match_hint = f'未找到「{kw_base}」相关团期，该产品可能暂无排期'

                # 按 travelType 分组
                by_type = {}
                for g in filtered:
                    tt = g.get("travelType", "")
                    ttd = g.get("travelTypeDesc", "")
                    if tt not in by_type:
                        by_type[tt] = {
                            "travel_type": tt,
                            "title": ttd,
                            "tags": "",
                            "nights": None,
                            "days": None,
                            "travel_type_desc": ttd,
                            "category_sub_desc": g.get("categorySubDesc", ""),
                            "specifications_desc": g.get("specificationsDesc", ""),
                        }
                    if "groups" not in by_type[tt]:
                        by_type[tt]["groups"] = []
                    by_type[tt]["groups"].append(g)

                result_products = []
                for p in by_type.values():
                    gs = p.pop("groups", [])
                    # 过滤：仅保留直连(CRS)、已上架(sta 为空/'I')、有剩余库存
                    gs = [g for g in gs
                          if g.get("ota") != "OTA"
                          and g.get("sta") in (None, "", "I")
                          and g.get("saleNum", 0) > 0]
                    gs.sort(key=lambda x: x.get("groupBeginDate", ""))
                    if month:
                        month_gs = [g for g in gs if g.get("groupBeginDate", "").startswith(month)]
                        if month_gs:
                            gs = month_gs
                    # 补充元数据（取第一条团期的字段）
                    if gs:
                        p["itinerary_desc"] = gs[0].get("itineraryDesc", "")
                        p["category_sub_desc"] = gs[0].get("categorySubDesc", "")
                        p["specifications_desc"] = gs[0].get("specificationsDesc", "")
                    p["groups"] = [
                        {
                            "code": g.get("travelGroupCode", ""),
                            "begin": g.get("groupBeginDate", "")[:10],
                            "end": g.get("groupEndDate", "")[:10],
                            "price": g.get("startingPrice", 0),
                            "remaining": g.get("saleNum", 0),
                            "total": g.get("productNum", 0),
                            "sold": g.get("soldNum", 0),
                        }
                        for g in gs[:max_groups]
                    ]
                    result_products.append(p)

                return jsonify({
                    "success": True,
                    "keyword": keyword,
                    "month": month,
                    "source": "fallback_group_api",
                    "no_match_hint": no_match_hint if not result_products else "",
                    "products": result_products
                })

            except Exception as e:
                import traceback
                return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()})

        # 有向量库结果：逐个查团期
        result_products = []
        for p in matched_products:
            tid = p.get("travel_type")
            if not tid:
                p["groups"] = []
                result_products.append(p)
                continue

            try:
                all_groups = []
                for page in [0, 100]:
                    data = api_post(
                        f"{GROUP_API}?firstResult={page}&pageSize=100&unitCode=SONGTSAM",
                        {"travelType": tid},
                        token=token
                    )
                    groups = data.get("retVal", {}).get("datas", [])
                    if isinstance(groups, list):
                        all_groups.extend(groups)

                # 去重
                seen_code = set()
                unique = []
                for g in all_groups:
                    code = g.get("travelGroupCode", "")
                    if code and code not in seen_code:
                        seen_code.add(code)
                        unique.append(g)

                # 过滤：仅保留直连(CRS)、已上架(sta 为空/'I')、有剩余库存
                clean = [g for g in unique
                         if g.get("ota") != "OTA"
                         and g.get("sta") in (None, "", "I")
                         and g.get("saleNum", 0) > 0]
                clean.sort(key=lambda x: x.get("groupBeginDate", ""))

                # 用 API 团期数据补充元数据
                if clean:
                    p["itinerary_desc"] = clean[0].get("itineraryDesc", "") or p.get("title", "")
                    p["category_sub_desc"] = clean[0].get("categorySubDesc", "") or "主题团"
                    p["specifications_desc"] = clean[0].get("specificationsDesc", "") or ""

                # 优先指定月份
                display = clean
                if month:
                    month_gs = [g for g in clean if g.get("groupBeginDate", "").startswith(month)]
                    if month_gs:
                        display = month_gs

                p["groups"] = [
                    {
                        "code": g.get("travelGroupCode", ""),
                        "begin": g.get("groupBeginDate", "")[:10],
                        "end": g.get("groupEndDate", "")[:10],
                        "price": g.get("startingPrice", 0),
                        "remaining": g.get("saleNum", 0),
                        "total": g.get("productNum", 0),
                        "sold": g.get("soldNum", 0),
                    }
                    for g in display[:max_groups]
                ]
            except Exception as e:
                p["groups"] = []

            result_products.append(p)

        # 无匹配时的友好提示
        no_hint = ""
        if not result_products:
            import re as re_mod
            kw_base = re_mod.sub(r'\s*\d+晚\d+天\s*$', '', keyword).strip()
            no_hint = f'未找到「{kw_base or keyword}」相关团期，该产品可能暂无排期'

        return jsonify({
            "success": True,
            "keyword": keyword,
            "month": month,
            "source": "vector_db",
            "no_match_hint": no_hint,
            "products": result_products
        })

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()})


def _get_user_code_from_token(token: str) -> str:
    """从 JWT token 中解码出 userCode（用于库存API）"""
    try:
        import base64
        parts = token.split('.')
        if len(parts) >= 2:
            payload_b64 = parts[1] + '=' * (4 - len(parts[1]) % 4)
            payload = json.loads(base64.b64decode(payload_b64))
            return payload.get("userCode", "HL") or "HL"
    except Exception:
        pass
    return "HL"


@app.route("/api/inventory-direct", methods=["POST"])
def inventory_direct():
    """
    直查酒店库存接口（后端代理，解决前端CORS）
    请求: {
        "hotel_codes": ["STNJBW"],
        "begin_date": "2026-05-01",
        "end_date": "2026-05-03"
    }
    """
    INVENTORY_API_URL = "https://gds.songtsam.com/product-room/bks/productType/listPrSingleOrderRoom"
    EXCLUDE_KEYWORDS = ['OTA', '飞猪', '携程']

    try:
        body = request.get_json() or {}
        hotel_codes = body.get("hotel_codes", [])
        begin_date = body.get("begin_date", "")
        end_date = body.get("end_date", "")

        if not hotel_codes or not begin_date or not end_date:
            return jsonify({"success": False, "error": "缺少参数：hotel_codes/begin_date/end_date"})

        token = get_token()
        user_code = _get_user_code_from_token(token)
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"} if token else {"Content-Type": "application/json"}

        resp = requests.post(INVENTORY_API_URL, headers=headers, json={
            "hotelGroupCode": "SONGTSAM",
            "otaChannel": "CRS",
            "maxMemberLevel": "002",
            "unitCode": "SONGTSAM",
            "beginDate": begin_date,
            "endDate": end_date,
            "hotelCodes": hotel_codes,
            "userCode": user_code,
        }, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # 过滤：sta 为空/I 均可，避开 OTA 和目的地套餐
        entries = data.get("retVal", []) or []
        filtered = [e for e in entries
                    if (e.get("sta") in (None, "", "I"))
                    and not any(kw in (e.get("productDesc") or "") for kw in EXCLUDE_KEYWORDS)
                    and "目的地套餐" not in (e.get("categorySubDesc") or "")]

        return jsonify({"success": True, "retVal": filtered})

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


# ============ AI 推荐路由 ============
@app.route("/api/ai-recommend", methods=["POST"])
def ai_recommend():
    """
    AI推荐接口（SSE流式）
    请求: {"query": "2人情侣去林芝看桃花", "preferred_month": "2026-05"}
    返回: text/event-stream
      data: {"type":"products","data":{...}}    # 先推产品结构化数据
      data: {"type":"token","content":"..."}    # 再流式推 AI 分析文字
      data: {"type":"done"}                     # 结束
    """
    import json as _json
    from flask import Response, stream_with_context

    try:
        body = request.get_json()
        query = body.get("query", "")
        preferred_month = body.get("preferred_month", None)
        if not query:
            return jsonify({"success": False, "error": "请输入您的需求"})

        # 1. 解析需求
        req = parse_requirements(query)
        if not preferred_month:
            m = re.search(r'(\d+)月', query)
            if m:
                preferred_month = f"2026-{int(m.group(1)):02d}"

        strategy = get_display_strategy(req.get("people", 0), req.get("type"), req.get("trip_type"))

        # 2. 向量搜索
        vector_results = []
        if HAS_VECTOR_DB:
            try:
                vector_results = query_vectorstore(query, n_results=100)
            except Exception:
                pass
        for p in vector_results:
            score_product(p, req)
        vector_results.sort(key=lambda x: x.get("score", 0), reverse=True)

        # 3. 取Top20，查团期
        top_products = vector_results[:20]
        token = get_token()
        for p in top_products:
            tid = p.get("metadata", {}).get("travel_type")
            p["groups"] = query_groups(tid, token, preferred_month=preferred_month) if tid else []

        # 4. 按形态分组（复用原逻辑）
        by_type = {"私享管家": [], "主题团": [], "自由行": []}
        season = req.get("season", "")
        for p in top_products:
            meta = p.get("metadata", {})
            product_tags = meta.get("tags", "")
            category_sub = meta.get("category_sub", "")
            title = meta.get("title", "")
            supported = [t for t in ["私享管家", "主题团", "自由行"] if t in product_tags or t in category_sub]
            if not supported:
                continue
            p["supported_types"] = supported
            is_season = (season == "杜鹃季" and "杜鹃季" in title) or \
                        (season == "桃花季" and ("桃花季" in title or "桃花季" in product_tags))
            if is_season:
                for ptype in supported:
                    by_type[ptype].append(p)
            else:
                by_type[supported[0]].append(p)

        products_by_type = {}
        for ptype in strategy.get("sort_priority", ["私享管家", "主题团", "自由行"]):
            type_products = sorted(by_type.get(ptype, []),
                                   key=lambda x: (1 if x.get("groups") else 0, x.get("score", 0)),
                                   reverse=True)
            items = []
            for p in type_products[:3]:
                meta = p.get("metadata", {})
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
                        {"begin": g.get("groupBeginDate", "")[:10],
                         "price": g.get("startingPrice", 0),
                         "remaining": g.get("saleNum", 0),
                         "code": g.get("travelGroupCode", "")}
                        for g in p.get("groups", [])
                    ],
                })
            if items:
                products_by_type[ptype] = items

        structured = {
            "success": True,
            "requirements": req,
            "strategy": strategy,
            "products_by_type": products_by_type,
        }

        # 5. 构造给 AI 的 prompt
        product_list_lines = []
        for ptype, items in products_by_type.items():
            for item in items:
                title = item.get("title", "")
                nights = item.get("nights", "")
                days = item.get("days", "")
                tags_raw = item.get("tags", "")
                groups = item.get("groups", [])
                duration = f"{nights}晚{days}天" if nights else ""
                tags_str = "、".join([t for t in tags_raw.split(",") if t and t not in ["私享管家","主题团","自由行"]][:4])
                groups_str = "、".join([f"{g['begin']} ¥{g['price']}/人 剩{g['remaining']}位" for g in groups]) if groups else "暂无近期团期"
                product_list_lines.append(
                    f"【{ptype}】{title} {duration} | 标签: {tags_str} | 团期: {groups_str} | 推荐理由: {', '.join(item.get('reasons', []))}"
                )
        product_list_str = "\n".join(product_list_lines) if product_list_lines else "（未检索到相关产品）"

        tip = strategy.get("tip", "")
        system_prompt = (
            "你是松赞旅行的金牌顾问小多吉，专注于滇藏川高端精品旅行。"
            "你的风格：热情、专业、简洁，像朋友一样说话，不过度推销。"
            "重要：禁止捏造不在列表中的产品或团期数字。"
        )
        user_prompt = (
            f"客户需求：{query}\n"
            f"策略提示：{tip}\n\n"
            f"以下是为客户匹配的产品列表：\n{product_list_str}\n\n"
            "请根据以上产品，用3-5句话帮客户做一个简短、有温度的推荐总结。"
            "格式：先说一句为什么推荐，再列2-3个重点产品（名称+亮点+有团期优先），最后一句鼓励客户咨询。"
            "不要使用Markdown符号，直接纯文字输出。"
        )

        api_key = get_ai_api_key()

        def generate():
            # 先推结构化产品数据
            yield f"data: {_json.dumps({'type': 'products', 'data': structured}, ensure_ascii=False)}\n\n"

            if not api_key:
                yield f"data: {_json.dumps({'type': 'token', 'content': '（AI服务未配置，请设置 ZHIPU_API_KEY 环境变量）'}, ensure_ascii=False)}\n\n"
                yield f"data: {_json.dumps({'type': 'done'})}\n\n"
                return

            # 调用 AI 流式接口
            try:
                ai_resp = requests.post(
                    AI_API_URL,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": AI_MODEL,
                        "stream": True,
                        "thinking": {"type": "off"},  # 关闭思维链，直接出答案
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt},
                        ]
                    },
                    stream=True,
                    timeout=30
                )
                for line in ai_resp.iter_lines():
                    if not line:
                        continue
                    line_str = line.decode("utf-8") if isinstance(line, bytes) else line
                    if line_str.startswith("data: "):
                        chunk_str = line_str[6:]
                        if chunk_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = _json.loads(chunk_str)
                            delta = chunk.get("choices", [{}])[0].get("delta", {})
                            content = delta.get("content", "")
                            if content:
                                yield f"data: {_json.dumps({'type': 'token', 'content': content}, ensure_ascii=False)}\n\n"
                        except Exception:
                            pass
            except Exception as e:
                yield f"data: {_json.dumps({'type': 'token', 'content': f'（AI服务暂时不可用：{str(e)[:50]}）'}, ensure_ascii=False)}\n\n"

            yield f"data: {_json.dumps({'type': 'done'})}\n\n"

        return Response(stream_with_context(generate()), mimetype="text/event-stream",
                        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    except Exception as e:
        import traceback
        return jsonify({"success": False, "error": str(e), "trace": traceback.format_exc()})


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
