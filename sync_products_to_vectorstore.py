#!/usr/bin/env python3
"""
松赞旅行产品向量库同步脚本
- 从松赞API获取所有产品数据
- 构建产品文本描述
- 存入ChromaDB向量库
"""

import json
import os
import re
import html
from typing import Optional

import chromadb
from chromadb.config import Settings
import ollama

# ============== 配置 ==============
SONGTSAM_API_BASE = "https://gds.songtsam.com"
LOGIN_URL = f"{SONGTSAM_API_BASE}/uc-web/v2/password/loginSSO"
PRODUCT_LIST_URL = f"{SONGTSAM_API_BASE}/product-journey/bks/travelproduct/listTravelProductTypePage"
PRODUCT_DETAIL_URL = f"{SONGTSAM_API_BASE}/product-journey/bks/travelproduct/getTravelProductType"
ITINERARY_URL = f"{SONGTSAM_API_BASE}/product-journey/bks/itinerary/getTravelProductitinerary"

# 登录凭据（从环境变量或硬编码）
LOGIN_PAYLOAD = {
    "orgCode": "SONGTSAM",
    "userCode": "13678767674",
    "password": "L+THB3NojO1oYnHv2u6D/QdwZQQqCQYWtM8DCXBerm5A6y32zcNgf2ojbGsjun6vhiKfYrUuvNrrFlehIkJJSVrO6k3jHzZrVyohtfnD8mVdDOe//bhelrR5DURe+L+1iJxe+DtATNasuGpYePz6mh0WlkuycuIdEhqSsPL0GP/xUrHWC+pYxygsIie0tcV2UK79aniKd4kggloOn6IkFytEKqOc2RjmWFUFR243rxeN6trKv9DKfCtOJ7LxKvbnCKNwhJ73p3jrbI18En26xiqXl9Dsj/B0yfCCxLcYbPMmzcLcxAbYISqCKQGYdeLgSGKlyXg3A/P8kmwtBAx23Q=="
}

# 向量库路径
CHROMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db")
COLLECTION_NAME = "songtsam_products"

# ============== API调用 ==============

def login() -> Optional[str]:
    """登录获取Token"""
    import urllib.request
    import urllib.error

    data = json.dumps(LOGIN_PAYLOAD).encode("utf-8")
    req = urllib.request.Request(LOGIN_URL, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            if result.get("result") == 0:
                return result["retVal"]["jwtToken"]
    except Exception as e:
        print(f"登录失败: {e}")
    return None


def api_get(url: str, token: str, params: dict = None) -> Optional[dict]:
    """GET请求API"""
    import urllib.request
    import urllib.parse

    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"API请求失败 {url}: {e}")
    return None


def get_all_products(token: str) -> list:
    """获取所有产品列表"""
    products = []
    page_size = 50
    offset = 0

    while True:
        params = {
            "firstResult": offset,
            "pageSize": page_size,
            "sta": "R,I",  # 在售+暂不售
            "unitCode": "SONGTSAM"
        }
        result = api_get(PRODUCT_LIST_URL, token, params)
        if not result or not result.get("retVal"):
            break

        datas = result["retVal"].get("datas", [])
        if not datas:
            break

        products.extend(datas)
        print(f"已获取产品: {len(products)}")
        if len(datas) < page_size:
            break
        offset += page_size

    return products


def get_product_detail(travel_type: str, token: str) -> Optional[dict]:
    """获取产品基础信息"""
    return api_get(PRODUCT_DETAIL_URL, token, {"travelType": travel_type, "unitCode": "SONGTSAM"})


def get_itinerary(travel_type: str, token: str) -> Optional[dict]:
    """获取产品行程详情"""
    return api_get(ITINERARY_URL, token, {"travelType": travel_type, "unitCode": "SONGTSAM"})


# ============== 文本构建 ==============

def strip_html(text: str) -> str:
    """去除HTML标签并解码HTML实体"""
    if not text:
        return ""
    # 先解码HTML实体
    text = html.unescape(text)
    # 去除HTML标签
    text = re.sub(r"<[^>]+>", " ", text)
    # 清理多余空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_product_text(detail: dict, itinerary: dict) -> str:
    """构建产品的完整文本描述（用于embedding）"""

    parts = []

    # 1. 基本信息
    title = detail.get("title", "")
    subtitle = strip_html(detail.get("subtitle", ""))
    parts.append(f"产品名称: {title}")
    if subtitle:
        parts.append(f"产品简介: {subtitle}")

    # 2. 行程概述
    itinerary_desc = detail.get("productItineraryDesc", "")
    if itinerary_desc:
        parts.append(f"行程路线: {itinerary_desc}")

    # 3. 集合/散团地
    rendezvous = detail.get("rendezvousDesc", "")
    dissolution = detail.get("dissolutionDesc", "")
    if rendezvous or dissolution:
        parts.append(f"集合地: {rendezvous}，散团地: {dissolution}")

    # 4. 产品标签
    tags = [t.get("tageDesc", "") for t in detail.get("tageDtos", []) if t.get("tageDesc")]
    if tags:
        parts.append(f"产品标签: {', '.join(tags)}")

    # 5. 价格说明
    illustrate = strip_html(detail.get("illustrate", ""))
    if illustrate:
        parts.append(f"价格说明: {illustrate}")

    # 6. 行程详情
    if itinerary and itinerary.get("itineraryDtos"):
        itinerary_data = itinerary["itineraryDtos"][0]
        days = itinerary_data.get("itineraryDays", 0)
        nights = itinerary_data.get("itineraryLatency", 0)
        parts.append(f"行程天数: {days}天{nights}晚")

        category_sub = itinerary_data.get("categorySubDesc", "")
        if category_sub:
            parts.append(f"产品类型: {category_sub}")

        # 每天行程
        day_list = []
        for day in itinerary_data.get("dayDtos", []):
            day_num = day.get("dayNum", "")
            city = day.get("cityDesc", "")
            desc = strip_html(day.get("descript", ""))

            # 酒店
            hotels = []
            for d in day.get("dayDetailDtos", []):
                for h in d.get("hotelDtos", []):
                    hotels.append(h.get("hotelDesc", ""))
            hotel_str = "，".join(hotels) if hotels else ""

            # 活动
            activities = []
            for d in day.get("dayDetailDtos", []):
                for a in d.get("activityDtos", []):
                    act_name = a.get("activityName", "") or a.get("activityDesc", "")
                    if act_name:
                        activities.append(act_name)
            act_str = "；".join(activities) if activities else ""

            day_text = f"第{day_num}天"
            if city:
                day_text += f" {city}"
            if hotel_str:
                day_text += f"，住{hotel_str}"
            if desc:
                day_text += f"。{desc[:100]}..."
            if act_str:
                day_text += f" 活动: {act_str}"
            day_list.append(day_text)

        if day_list:
            parts.append("每日行程:\n" + "\n".join(day_list))

        # 行程亮点
        features = []
        for f in itinerary_data.get("featureDtos", []):
            summarize = f.get("summarize", "")
            if summarize:
                features.append(summarize)
        if features:
            parts.append(f"行程亮点: {', '.join(features)}")

        # 费用包含/不含
        cost_includes = strip_html(itinerary_data.get("costIncludes", ""))
        cost_excluding = strip_html(itinerary_data.get("costExcluding", ""))
        if cost_includes:
            parts.append(f"费用包含: {cost_includes[:300]}")
        if cost_excluding:
            parts.append(f"费用不含: {cost_excluding[:200]}")

    return "\n".join(parts)


# ============== 向量库操作 ==============

def get_embedding(text: str, model: str = "nomic-embed-text") -> list:
    """通过Ollama获取文本embedding"""
    try:
        response = ollama.embeddings(model=model, prompt=text)
        return response["embedding"]
    except Exception as e:
        print(f"Embedding失败: {e}")
        return None


def init_chroma():
    """初始化ChromaDB"""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    # 删除旧集合（如果存在）
    try:
        client.delete_collection(COLLECTION_NAME)
    except:
        pass
    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"description": "松赞旅行产品知识库"}
    )
    return client, collection


def sync_all():
    """同步所有产品到向量库"""
    print("=" * 50)
    print("松赞旅行产品向量库同步")
    print("=" * 50)

    # 1. 登录
    print("\n[1/5] 登录...")
    token = login()
    if not token:
        print("登录失败!")
        return
    print("登录成功")

    # 2. 获取产品列表
    print("\n[2/5] 获取产品列表...")
    products = get_all_products(token)
    print(f"共找到 {len(products)} 个产品")
    if not products:
        return

    # 3. 初始化向量库
    print("\n[3/5] 初始化向量库...")
    client, collection = init_chroma()

    # 4. 逐个处理产品
    print("\n[4/5] 同步产品到向量库...")
    ids = []
    embeddings = []
    documents = []
    metadatas = []

    for i, product in enumerate(products):
        travel_type = product.get("travelType", "")
        if not travel_type:
            continue

        print(f"  处理 [{i+1}/{len(products)}] {product.get('title', '')}...")

        # 获取详情
        detail_result = get_product_detail(travel_type, token)
        detail = detail_result.get("retVal", {}) if detail_result else {}

        # 获取行程
        itinerary_result = get_itinerary(travel_type, token)
        itinerary = itinerary_result.get("retVal", {}) if itinerary_result else {}

        # 构建文本
        text = build_product_text(detail, itinerary)
        if not text.strip():
            print(f"    跳过: 无文本内容")
            continue

        # 获取embedding
        embedding = get_embedding(text)
        if not embedding:
            print(f"    跳过: embedding失败")
            continue

        # 提取元数据
        meta = {
            "travel_type": travel_type,
            "title": detail.get("title", product.get("title", "")),
            "series": detail.get("seriesName", product.get("seriesName", "")),
            "category_sub": detail.get("categorySubDesc", ""),
            "rendezvous": detail.get("rendezvousDesc", ""),
            "dissolution": detail.get("dissolutionDesc", ""),
            "itinerary_days": itinerary.get("itineraryDtos", [{}])[0].get("itineraryDays", 0) if itinerary.get("itineraryDtos") else 0,
            "itinerary_nights": itinerary.get("itineraryDtos", [{}])[0].get("itineraryLatency", 0) if itinerary.get("itineraryDtos") else 0,
        }
        # 标签
        tags = [t.get("tageDesc", "") for t in detail.get("tageDtos", [])]
        meta["tags"] = ",".join(tags)

        ids.append(travel_type)
        embeddings.append(embedding)
        documents.append(text)
        metadatas.append(meta)

    # 批量写入
    print(f"\n  写入 {len(ids)} 条数据到向量库...")
    if ids:
        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    print(f"\n[5/5] 同步完成!")
    print(f"  总产品数: {len(products)}")
    print(f"  成功入库: {len(ids)}")
    print(f"  向量库路径: {CHROMA_PATH}")


if __name__ == "__main__":
    sync_all()
