#!/usr/bin/env python3
"""
松赞产品推荐助手 - 后端API服务
提供推荐算法接口，支持微信小程序调用
"""
import sys
import time
import json
import re
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

# ============ Flask App ============
app = Flask(__name__)
CORS(app)  # 允许跨域，支持小程序调用


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
    """解析用户需求"""
    req = {
        "days": None,
        "people": None,
        "budget": None,
        "type": None,  # 自由行/私享管家/主题团
        "season": None,
        "location": None,
        "tag": None,
        "trip_type": None,  # 情侣/家庭/闺蜜/银发/其他
        "with_elder_kids": False,
        "is_foreigner": False,
        "member_level": None,
    }

    # 出行类型识别
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

    # 是否带老人小孩
    if any(kw in query for kw in ["带小孩", "带小朋友", "带孩子", "亲子", "全家", "带爸妈", "带父母", "老人"]):
        req["with_elder_kids"] = True

    # 是否外籍
    if any(kw in query for kw in ["外籍", "外国人", "老外"]):
        req["is_foreigner"] = True

    # 会员等级
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

    # 人数
    people_match = re.search(r"(\d+)\s*[人大客位]", query)
    if people_match:
        req["people"] = int(people_match.group(1))
    elif req["trip_type"] == "情侣":
        req["people"] = 2

    # 产品类型
    if "自由行" in query:
        req["type"] = "自由行"
    elif "私享管家" in query or "私享" in query:
        req["type"] = "私享管家"
    elif "主题团" in query:
        req["type"] = "主题团"

    # 季节
    season_keywords = {
        "桃花季": ["桃花", "桃花节"],
        "杜鹃季": ["杜鹃", "杜鹃花"],
        "亲子": ["亲子", "小朋友"],
        "夏季": ["夏季", "夏天", "避暑"],
    }
    for season, keywords in season_keywords.items():
        if any(kw in query for kw in keywords):
            req["season"] = season
            break

    # 目的地
    location_keywords = {
        "拉萨": ["拉萨", "布达拉"],
        "林芝": ["林芝", "南迦巴瓦", "巴松措", "达林"],
        "波密": ["波密", "来古"],
        "梅里": ["梅里", "德钦"],
        "香格里拉": ["香格里拉", "奔子栏", "塔城", "绿谷"],
        "普洱": ["普洱"],
        "丽江": ["丽江"],
    }
    for loc, keywords in location_keywords.items():
        if any(kw in query for kw in keywords):
            req["location"] = loc
            break

    # 标签
    tag_keywords = {
        "亲子度假": ["亲子度假"],
        "亲子研学": ["亲子研学"],
        "深度户外": ["深度户外", "徒步", "穿越"],
        "轻户外": ["轻户外"],
        "低海拔": ["低海拔"],
        "度假休闲": ["度假休闲", "度假", "休闲"],
        "美食美酒": ["美食美酒", "美食"],
        "摄影爱好": ["摄影爱好", "摄影"],
        "高原花季": ["桃花", "杜鹃"],
    }
    for tag, keywords in tag_keywords.items():
        if any(kw in query for kw in keywords):
            req["tag"] = tag
            break

    return req


# ============ 展示策略 ============
def get_display_strategy(people: int, user_type: str, trip_type: str) -> dict:
    """获取推荐展示策略"""
    # 用户指定形态
    if user_type:
        return {
            "mode": "single",
            "show_types": [user_type],
            "tip": f"为您筛选【{user_type}】产品"
        }

    # 按出行类型
    if trip_type == "情侣":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "自由行", "主题团"],
            "sort_priority": ["私享管家", "自由行", "主题团"],
            "tip": "💑 情侣出行推荐【私享管家】，私密浪漫管家专属服务"
        }
    if trip_type == "家庭":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团"],
            "sort_priority": ["私享管家", "主题团"],
            "tip": "👨‍👩‍👧‍👦 家庭出行推荐【私享管家】，管家照顾老小更贴心"
        }
    if trip_type == "银发":
        return {
            "mode": "single",
            "show_types": ["私享管家"],
            "tip": "👴👵 银发出行推荐【私享管家】，节奏灵活可根据身体状况调整"
        }
    if trip_type == "闺蜜":
        return {
            "mode": "multi",
            "show_types": ["私享管家", "自由行"],
            "sort_priority": ["私享管家", "自由行"],
            "tip": "👭 闺蜜出行推荐【私享管家】或【自由行】，轻松自由"
        }

    # 按人数
    if people == 1:
        return {
            "mode": "single",
            "show_types": ["主题团"],
            "tip": "1人出行推荐【主题团】，可拼团和陌生人拼房免单房差"
        }
    if people == 2:
        return {
            "mode": "multi",
            "show_types": ["私享管家", "主题团", "自由行"],
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
            "tip": "4人通常为标品变形，可选主题团（需确认团期）"
        }
    if people and people >= 5:
        return {
            "mode": "single",
            "show_types": ["主题团"],
            "tip": f"{people}人【主题团】最划算，8-12人标准规模拼团分摊成本"
        }

    return {
        "mode": "multi",
        "show_types": ["私享管家", "主题团", "自由行"],
        "tip": "以下3种玩法各有特色，您可以选择适合您的"
    }


# ============ 评分逻辑 ============
def score_product(product: dict, req: dict) -> tuple:
    """评分产品，返回(分数, 原因列表)"""
    score = 0
    reasons = []
    tags = product.get("tags", [])
    types = product.get("types", [])
    destinations = product.get("destinations", [])

    # 形态×人数匹配
    if req.get("people"):
        people = req["people"]
        if people == 1 and "主题团" in types:
            score += 1.5
            reasons.append("1人可拼团免单房差")
        if people == 2 and "私享管家" in types:
            score += 1.5
        if people == 2 and "自由行" in types:
            score += 0.8
        if 3 <= people <= 4 and "主题团" in types:
            score += 1.0
        if people >= 5 and "主题团" in types:
            score += 1.5

    # 出行类型匹配
    if req.get("trip_type"):
        tt = req["trip_type"]
        if tt == "情侣" and "私享管家" in types:
            score += 1.2
            reasons.append("💑 情侣首选：私密小团")
        if tt == "家庭" and any(t in ["亲子度假", "亲子研学", "亲子"] for t in tags):
            score += 1.5
            reasons.append("👨‍👩‍👧‍👦 家庭首选：亲子产品")
        if tt == "家庭" and "私享管家" in types:
            score += 0.8
            reasons.append("管家照顾老小更贴心")
        if tt == "银发" and any(t in ["低海拔", "度假休闲", "疗愈"] for t in tags):
            score += 1.5
            reasons.append("👴👵 银发首选：低海拔/轻松休闲")
        if tt == "银发" and "深度户外" in tags:
            score -= 0.8
            reasons.append("⚠️ 深度户外强度较大")
        if tt == "闺蜜" and any(t in ["轻户外", "美食美酒", "摄影爱好", "度假休闲"] for t in tags):
            score += 1.2
            reasons.append("👭 闺蜜推荐：拍照美食两不误")

    # 季节匹配
    if req.get("season"):
        season = req["season"]
        if season in ["桃花季", "杜鹃季"] and "高原花季" in tags:
            score += 1.5
        if season == "亲子" and any(t in ["亲子度假", "亲子研学"] for t in tags):
            score += 1.2

    # 目的地匹配
    if req.get("location") and req["location"] in destinations:
        score += 1.0
        reasons.append(f"目的地匹配: {req['location']}")

    # 天数匹配
    if req.get("days") and product.get("nights"):
        if abs(req["days"] - (product["nights"] + 1)) <= 1:
            score += 0.5

    # 风险提示
    if req.get("is_foreigner") and product.get("risks") and "入藏函" in product["risks"]:
        reasons.append("⚠️ 注意：西藏行程需入藏函，请提前确认")

    return score, reasons


# ============ API 路由 ============
@app.route("/api/recommend", methods=["POST"])
def recommend():
    """
    推荐接口
    请求: {"query": "2人情侣去林芝看桃花"}
    返回: {"success": true, "data": {...}}
    """
    try:
        data = request.get_json()
        query = data.get("query", "")

        if not query:
            return jsonify({"success": False, "error": "请输入您的需求"})

        # 解析需求
        req = parse_requirements(query)
        strategy = get_display_strategy(req.get("people", 0), req.get("type"), req.get("trip_type"))

        # 向量搜索
        if HAS_VECTOR_DB:
            try:
                vector_results = query_vectorstore(query, n_results=50)
            except Exception as e:
                vector_results = []
        else:
            vector_results = []

        # 筛选和评分
        matched = []
        for item in vector_results:
            metadata = item.get("metadata", {})
            # tags字段包含产品类型和标签，如"主题团,私享管家,自然景观"
            all_tags = metadata.get("tags", "").split(",") if metadata.get("tags") else []
            # 产品类型（主题团/私享管家/自由行）
            product_types = [t for t in all_tags if t in ["主题团", "私享管家", "自由行"]]
            # 实际标签（排除产品类型）
            product_tags = [t for t in all_tags if t not in ["主题团", "私享管家", "自由行"]]
            product_dest = metadata.get("destinations", "").split(",") if metadata.get("destinations") else []
            
            # 从title中提取名称
            title = metadata.get("title", item.get("id", ""))
            name = title.split("|")[0].strip() if "|" in title else title

            # 形态筛选（默认显示所有类型）
            if strategy["show_types"] and strategy["show_types"] != ["私享管家", "主题团", "自由行"]:
                if not any(t in product_types for t in strategy["show_types"]):
                    continue

            product = {
                "id": item.get("id"),
                "name": name or title,
                "short_name": metadata.get("title", ""),
                "nights": metadata.get("itinerary_nights"),
                "days": metadata.get("itinerary_days"),
                "types": product_types,
                "tags": product_tags,
                "destinations": product_dest,
                "desc": metadata.get("title", ""),
                "rendezvous": metadata.get("rendezvous", ""),
                "dissolution": metadata.get("dissolution", ""),
                "risks": [],
                "distance": item.get("distance", 0),
            }

            # 评分
            score, reasons = score_product(product, req)
            product["score"] = score
            product["reasons"] = reasons

            # 会员折扣
            if req.get("member_level"):
                product["member_discount"] = req["member_level"]

            matched.append(product)

        # 排序
        if strategy.get("sort_priority"):
            def sort_key(p):
                type_idx = next((i for i, t in enumerate(strategy["sort_priority"]) if t in p.get("types", [])), 999)
                return (type_idx, -p.get("score", 0))
            matched.sort(key=sort_key)
        else:
            matched.sort(key=lambda p: -p.get("score", 0))

        # 取前5个
        matched = matched[:5]

        result = {
            "success": True,
            "query": query,
            "requirements": req,
            "strategy": strategy,
            "products": matched,
            "has_vector_db": HAS_VECTOR_DB,
        }

        return jsonify(result)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


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
