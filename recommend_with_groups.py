#!/usr/bin/env python3
"""
松赞产品推荐 + 团期查询一体化脚本
流程：推荐产品 → 查可预订团期 → 展示价格和库存
"""
import json
import sys
import time
import requests
import chromadb
import ollama
from pathlib import Path

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
ITINERARY_API = "https://gds.songtsam.com/product-journey/bks/itinerary/getTravelProductitinerary"
GROUP_API = "https://gds.songtsam.com/product-journey/bks/travelGroupProvider/listTravelGroupForOrder"
PRODUCT_API = "https://gds.songtsam.com/product-journey/bks/travelproduct/getTravelProductType"


# ============ 认证 ============
def get_token():
    """获取/刷新 Token"""
    try:
        mtime = TOKEN_FILE.stat().st_mtime
        if time.time() - mtime < TOKEN_EXPIRY:
            return TOKEN_FILE.read_text().strip()
    except:
        pass

    resp = requests.post(TOKEN_URL, headers=HEADERS, json=LOGIN_PAYLOAD, timeout=15)
    resp.raise_for_status()
    token = resp.json()["retVal"]["jwtToken"]
    TOKEN_FILE.write_text(token)
    return token


def api_get(url, params=None, token=None):
    """GET 请求（自动带 Token）"""
    if not token:
        token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def api_post(url, data, token=None):
    """POST 请求"""
    if not token:
        token = get_token()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    resp = requests.post(url, headers=headers, json=data, timeout=15)
    resp.raise_for_status()
    return resp.json()


# ============ 向量库 ============
def get_embedding(text: str):
    response = ollama.embeddings(model="nomic-embed-text", prompt=text)
    return response["embedding"]


def query_vectorstore(query_text: str, n_results: int = 100) -> list:
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
    import re

    # === 出行类型识别（优先于人数识别）===
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
        req["tag"] = "低海拔"  # 银发优先低海拔
    if req["trip_type"] == "家庭" and not req["season"]:
        req["season"] = "亲子"  # 家庭默认推荐亲子产品

    # === 目的地区域识别 ===
    region_keywords = {
        "西藏": ["西藏", "藏区", "藏地", "高原"],
        "云南": ["云南", "丽江"],
        "滇藏": ["滇藏"],
    }
    for region, keywords in region_keywords.items():
        if any(kw in query for kw in keywords):
            req["region"] = region
            break

    return req


# ============ 评分 ============
# 产品形态权重配置（根据人数动态调整）
# 
# 业务规则：
# - 1人：主题团（可拼团/和陌生人拼房免单房差）
# - 2人：私享管家/自由行/主题团 都可以
# - 3人：主题团 或 私享管家
# - 4人：标品变形，否则主题团
# - 5-7人：主题团
# - 8-12人：主题团（标准规模）
#
# 权重说明：分值越高表示越推荐
PRODUCT_TYPE_WEIGHTS = {
    "私享管家": {
        "default": 0.8,
        "by_people": {
            (1, 1): 0.2,   # 1人：主推主题团
            (2, 2): 1.5,   # 2人：私享管家最适合
            (3, 4): 1.2,   # 3-4人：私享管家合适
            (5, 999): 0.5, # 5人+：主题团更划算
        }
    },
    "主题团": {
        "default": 0.8,
        "by_people": {
            (1, 1): 1.5,   # 1人：主推主题团（可拼团免单房差）
            (2, 2): 1.0,   # 2人：主题团也OK
            (3, 4): 1.0,   # 3-4人：主题团合适（4人需标品变形）
            (5, 999): 1.5, # 5人+：主题团最划算
        }
    },
    "自由行": {
        "default": 0.5,
        "by_people": {
            (1, 1): 0.3,   # 1人：不太推荐（单房差问题）
            (2, 2): 0.8,   # 2人：自由行OK
            (3, 999): 0.2, # 3人+：自由行不太划算
        }
    },
}


def get_product_type_weight(product_type: str, people: int) -> tuple:
    """根据人数获取产品形态权重
    Returns: (weight, desc)
    """
    if not product_type:
        return 0, ""

    cfg = PRODUCT_TYPE_WEIGHTS.get(product_type, {"default": 0, "by_people": {}})

    # 按人数查权重
    for (low, high), weight in cfg.get("by_people", {}).items():
        if low <= people <= high:
            # 形态推荐说明
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

    # === 2. 产品形态×人数 适配（重要！）===
    # 注意：形态信息在 tags 字段（逗号分隔），不是 category_sub
    people = req.get("people") or 0
    product_tags = meta.get("tags", "")
    category_sub = meta.get("category_sub", "")

    # 从 tags 中提取所有支持的形态
    supported_types = []
    for ptype in ["私享管家", "主题团", "自由行"]:
        if ptype in product_tags or ptype in category_sub:
            supported_types.append(ptype)

    if people > 0 and supported_types:
        # 根据人数，给最适合的形态加权
        # 取人数最匹配的那个形态作为主推荐
        primary_type = supported_types[0]  # 第一个是API返回的主要形态
        weight, desc = get_product_type_weight(primary_type, people)
        if weight > 0:
            score += weight
            if desc:
                reasons.append(f"[{primary_type}] {desc}")

        # 如果产品支持多种形态，说明"可定制"
        if len(supported_types) > 1:
            type_names = "+".join(supported_types)
            reasons.append(f"可选形态: {type_names}")
    elif req.get("type"):
        # 用户指定了类型
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
        product_tags = meta.get("tags", "")
        if req["tag"] in product_tags:
            score += 1.0
            reasons.append(f"标签匹配: {req['tag']}")

    # === 6. 出行类型匹配（情侣/家庭/银发等）===
    trip_type = req.get("trip_type")
    if trip_type:
        product_tags = meta.get("tags", "")
        title = meta.get("title", "")

        if trip_type == "情侣":
            # 情侣优先私密形态
            if "私享管家" in product_tags or "私享管家" in category_sub:
                score += 1.2
                reasons.append("💑 情侣首选：私密小团，浪漫专属")
            elif "自由行" in product_tags:
                score += 0.6
                reasons.append("💑 情侣可选：自由浪漫")
            # 避免推荐主题团
            if "主题团" in supported_types and len(supported_types) == 1:
                score -= 0.5

        elif trip_type == "家庭":
            # 家庭优先亲子产品
            if any(t in product_tags for t in ["亲子度假", "亲子研学", "亲子"]):
                score += 1.5
                reasons.append("👨‍👩‍👧‍👦 家庭首选：亲子产品")
            elif "私享管家" in product_tags:
                score += 0.8
                reasons.append("👨‍👩‍👧‍👦 家庭可选：管家服务贴心")

        elif trip_type == "银发":
            # 银发优先低海拔、轻松节奏
            if any(t in product_tags for t in ["低海拔", "度假休闲", "疗愈"]):
                score += 1.5
                reasons.append("👴👵 银发首选：低海拔/轻松休闲")
            elif "轻户外" in product_tags:
                score += 0.8
                reasons.append("👴👵 银发可选：轻户外体验")
            # 避免深度户外
            if "深度户外" in product_tags:
                score -= 0.8
                reasons.append("⚠️ 深度户外强度较大，需评估身体状况")

        elif trip_type == "闺蜜":
            # 闺蜜推荐轻户外/美食美酒/摄影
            if any(t in product_tags for t in ["轻户外", "美食美酒", "摄影爱好", "度假休闲"]):
                score += 1.2
                reasons.append("👭 闺蜜推荐：拍照美食两不误")

    # === 7. 外籍提醒 ===
    if req.get("is_foreigner"):
        # 外籍去西藏需入藏函，提示风险
        title = meta.get("title", "")
        if "西藏" in title or "拉萨" in title or "林芝" in title:
            reasons.append("⚠️ 注意：西藏行程需入藏函，请提前确认")

    product["score"] = score
    product["reasons"] = reasons
    return score


# ============ 区域过滤 ============
SERIES_REGION_MAP = {
    "拉萨环线": "西藏",
    "冰川环线": "西藏",
    "梅里环线": "云南",
    "香格里拉环线": "云南",
    "昆明/普洱": "云南",
    "滇藏线": "滇藏",
}


def get_product_region(series: str) -> str:
    if series in SERIES_REGION_MAP:
        return SERIES_REGION_MAP[series]
    for key, region in SERIES_REGION_MAP.items():
        if key != "低空旅行" and series.startswith(key):
            return region
    if "低空" in series:
        if "西藏" in series:
            return "西藏"
        if "云南" in series:
            return "云南"
    return None


def filter_by_region(products: list, region: str) -> list:
    if not region:
        return products
    result = []
    for p in products:
        p_region = get_product_region(p.get("metadata", {}).get("series", ""))
        if p_region is None:
            result.append(p)
        elif p_region == region:
            result.append(p)
        elif region == "西藏" and p_region == "滇藏":
            result.append(p)
        elif region == "云南" and p_region == "滇藏":
            result.append(p)
    return result


# ============ 团期查询 ============
def query_groups(travel_type: str, token: str, max_groups: int = 3, preferred_month: str = None) -> list:
    """查询产品的可预订团期
    Args:
        travel_type: 产品ID
        token: 认证token
        max_groups: 最多返回团期数
        preferred_month: 优先月份，如 "2026-06"，会优先返回该月团期
    """
    try:
        # 合并两页（200条足够覆盖近半年）
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

        # 去重
        seen = set()
        unique_groups = []
        for g in all_groups:
            code = g.get("travelGroupCode", "")
            if code and code not in seen:
                seen.add(code)
                unique_groups.append(g)

        # 只取可预订的团期（剩余库存 > 0）
        available = [g for g in unique_groups if g.get("saleNum", 0) > 0]
        available.sort(key=lambda x: x.get("groupBeginDate", ""))

        # 优先返回指定月份的团期
        if preferred_month:
            month_groups = [g for g in available if g.get("groupBeginDate", "").startswith(preferred_month)]
            if month_groups:
                return month_groups[:max_groups]

        return available[:max_groups]
    except Exception as e:
        return []


def format_groups(groups: list) -> str:
    """格式化团期列表"""
    if not groups:
        return "  暂无可预订团期"

    lines = []
    for g in groups:
        begin = g.get("groupBeginDate", "")[:10]
        price = g.get("startingPrice", 0)
        remaining = g.get("saleNum", 0)   # saleNum = 剩余可售（还能收几人）
        total = g.get("productNum", 0)    # productNum = 计划成团人数
        group_code = g.get("travelGroupCode", "")  # 团期号
        biz_type = g.get("categorySubDesc", "")   # 业务类型
        status = "✅ 可订" if remaining > 0 else "❌ 已满"

        lines.append(
            f"  📅 {begin}  |  "
            f"【{biz_type}】  |  "
            f"¥{price:,.0f}/人  |  "
            f"剩余{remaining}位（满团{total}人）  |  "
            f"团期号: {group_code}  |  {status}"
        )
    return "\n".join(lines)


# ============ 形态推荐策略 ============
def get_display_strategy(people: int, user_specified_type: str = None, trip_type: str = None) -> dict:
    """根据人数和出行类型决定推荐策略

    业务规则：
    - 1人：主推主题团（可拼团/和陌生人拼房免单房差）
    - 2人：私享管家/自由行/主题团 都可以
    - 3人：主题团 或 私享管家
    - 4人：标品变形，否则主题团
    - 5-12人：主题团

    出行类型规则：
    - 情侣：主推私享管家（私密浪漫）
    - 家庭：私享管家（管家照顾老小方便）
    - 银发：私享管家（节奏灵活）
    - 闺蜜：私享管家/自由行（轻松自由）

    Returns: {
        "mode": "single" | "multi",  # 单形态推荐 or 多形态展示
        "show_types": ["私享管家", "主题团", "自由行"],  # 要展示的形态
        "sort_priority": [...],  # 形态排序优先级
        "tip": "提示语"
    }
    """
    if user_specified_type:
        return {
            "mode": "single",
            "show_types": [user_specified_type],
            "sort_priority": [user_specified_type],
            "tip": f"为您筛选【{user_specified_type}】产品"
        }

    # 根据出行类型调整策略
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

    if people == 0:
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

    # 5人+
    return {
        "mode": "single",
        "show_types": ["主题团"],
        "sort_priority": ["主题团"],
        "tip": f"{people}人【主题团】最划算，8-12人标准规模拼团分摊成本"
    }


# ============ 主流程 ============
def recommend_with_groups(query: str, top_k: int = 5) -> str:
    """推荐产品 + 查团期 + 价格"""
    import re
    token = get_token()

    print(f"\n🎯 需求: {query}")

    req = parse_requirements(query)
    print(f"📋 解析: {json.dumps(req, ensure_ascii=False)}")

    # 1. 向量库语义搜索
    products = query_vectorstore(query, n_results=100)
    if not products:
        return "未找到相关产品"

    # 2. 规则评分排序
    for p in products:
        score_product(p, req)
    products.sort(key=lambda x: x["score"] + abs(x.get("distance", 0)) * 0.01, reverse=True)

    # 2.1 目的地区域过滤
    if req.get("region"):
        products = filter_by_region(products, req["region"])

    # 3. 提取优先月份
    current_year = "2026"
    preferred_month = None
    m = re.search(r'(\d+)月', query)
    if m:
        month = int(m.group(1))
        preferred_month = f"{current_year}-{month:02d}"

    # 4. 构建季节×形态矩阵，同时预查询团期
    by_type = {"私享管家": [], "主题团": [], "自由行": []}

    # 先按评分排序取前20个产品
    scored_products = sorted(products, key=lambda x: x["score"], reverse=True)[:20]

    # 预查询所有产品的团期（避免重复查询）
    tid_to_groups = {}
    for p in scored_products:
        tid = p.get("metadata", {}).get("travel_type")
        if tid and tid not in tid_to_groups:
            groups = query_groups(tid, token, preferred_month=preferred_month)
            tid_to_groups[tid] = groups
        p["_cached_groups"] = tid_to_groups.get(tid, [])

    for p in scored_products:
        meta = p.get("metadata", {})
        product_tags = meta.get("tags", "")
        category_sub = meta.get("category_sub", "")
        title = meta.get("title", "")
        groups = p.get("_cached_groups", [])

        # 判断产品支持哪些形态
        supported = []
        for ptype in ["私享管家", "主题团", "自由行"]:
            if ptype in product_tags or ptype in category_sub:
                supported.append(ptype)

        if not supported:
            continue

        p["supported_types"] = supported

        # 杜鹃季/桃花季产品特殊处理：加入所有支持的形态
        season = req.get("season", "")
        is_season_product = False
        if season == "杜鹃季" and "杜鹃季" in title:
            is_season_product = True
        elif season == "桃花季" and ("桃花季" in title or "桃花季" in meta.get("tags", "")):
            is_season_product = True

        if is_season_product:
            for ptype in supported:
                by_type[ptype].append(p)
        else:
            by_type[supported[0]].append(p)

    # 5. 获取展示策略
    strategy = get_display_strategy(req.get("people", 0), req.get("type"), req.get("trip_type"))

    # 6. 构建输出
    lines = []
    lines.append(f"\n{'='*50}")
    lines.append(f"📋 {strategy['tip']}")
    lines.append(f"{'='*50}")

    # 按策略展示各形态产品
    for ptype in strategy["sort_priority"]:
        type_products = by_type.get(ptype, [])
        if not type_products:
            continue

        # 排序：有团期的优先，然后按评分
        def sort_key(p):
            groups = p.get("_cached_groups", [])
            has_groups = 1 if groups else 0
            return (has_groups, p.get("score", 0))
        type_products.sort(key=sort_key, reverse=True)

        lines.append(f"\n{'─'*50}")
        lines.append(f"🏷️  【{ptype}】")
        lines.append(f"{'─'*50}")

        # 每种形态最多展示3个产品（优先展示有团期的）
        shown = 0
        for i, p in enumerate(type_products, 1):
            if shown >= 3:
                break
            meta = p.get("metadata", {})
            title = meta.get("title", "未知产品")
            tags = meta.get("tags", "")
            reasons = " | ".join(p.get("reasons", []))
            score = p.get("score", 0)
            groups = p.get("_cached_groups", [])
            supported = p.get("supported_types", [])

            lines.append(f"\n  {i}. 【{title}】")
            if tags:
                lines.append(f"     标签: {tags}")
            if len(supported) > 1:
                lines.append(f"     🔄 也可选: " + "/".join([s for s in supported if s != ptype]))
            if reasons:
                lines.append(f"     推荐理由: {reasons}")

            # 展示团期
            if groups:
                lines.append(f"     📆 可预订团期:")
                for g in groups[:3]:
                    begin = g.get("groupBeginDate", "")[:10]
                    price = g.get("startingPrice", 0)
                    remaining = g.get("saleNum", 0)
                    total = g.get("productNum", 0)
                    biz_type = g.get("categorySubDesc", "")
                    lines.append(
                        f"       ✅ {begin} | 【{biz_type}】 | "
                        f"¥{price:,.0f}/人 | "
                        f"剩{remaining}位（满{total}人） | "
                        f"团期号: {g.get('travelGroupCode','')}"
                    )
            else:
                lines.append(f"     📆 暂无{preferred_month[5:] if preferred_month else '近期'}团期（可联系顾问确认）")

            shown += 1

    # 7. 形态说明卡片
    people = req.get("people", 0)
    if strategy["mode"] == "multi":
        lines.append(f"\n{'='*50}")
        lines.append(f"💡 3种玩法说明:")
        lines.append(f"{'='*50}")
        if people == 1:
            lines.append(f"  👥 主题团 — 1人可拼团，和陌生人拼房免单房差")
            lines.append(f"  🏠 私享管家 — 可包团，管家专属服务")
            lines.append(f"  🚗 自由行 — 不含管家，需解决单房差问题")
        else:
            lines.append(f"  🏠 私享管家 — 2-6人小团，管家全程服务，私密贴心")
            lines.append(f"  👥 主题团 — 多人拼团，性价比高，8-12人常见")
            lines.append(f"  🚗 自由行 — 含酒店+车司机，无管家，最自由灵活")
    elif people == 1:
        lines.append(f"\n{'='*50}")
        lines.append(f"💡 主题团说明:")
        lines.append(f"{'='*50}")
        lines.append(f"  👥 主题团 — 1人可拼团，和陌生人拼房可免单房差")
        lines.append(f"  📌 建议联系顾问确认是否有合适的团期可以拼入")

    return "\n".join(lines)


# ============ 入口 ============
if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else input("请输入需求: ")
    result = recommend_with_groups(q)
    print(result)
