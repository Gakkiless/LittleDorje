#!/usr/bin/env python3
"""
松赞旅行产品推荐助手
- 语义搜索：用户自然语言查询，返回匹配产品
- 推荐算法：基于用户需求（人数/天数/类型/预算/偏好）推荐最佳产品
"""

import os
import json
import argparse
import re

import chromadb
import ollama

# ============== 配置 ==============
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CHROMA_PATH = os.path.join(SCRIPT_DIR, "chroma_db")
COLLECTION_NAME = "songtsam_products"
EMBEDDING_MODEL = "nomic-embed-text"


def get_embedding(text: str, model: str = EMBEDDING_MODEL) -> list:
    """获取文本embedding"""
    response = ollama.embeddings(model=model, prompt=text)
    return response["embedding"]


def query_vectorstore(query_text: str, n_results: int = 5) -> list:
    """语义搜索向量库"""
    client = chromadb.PersistentClient(path=CHROMA_PATH)
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception:
        print("向量库未初始化，请先运行 sync_products_to_vectorstore.py")
        return []

    embedding = get_embedding(query_text)
    results = collection.query(
        query_embeddings=[embedding],
        n_results=n_results
    )

    products = []
    if results and results.get("ids"):
        for i in range(len(results["ids"][0])):
            products.append({
                "id": results["ids"][0][i],
                "document": results["documents"][0][i],
                "distance": results["distances"][0][i] if results.get("distances") else 0,
                "metadata": results["metadatas"][0][i] if results.get("metadatas") else {}
            })
    return products


def parse_requirements(query: str) -> dict:
    """从用户查询中解析需求"""
    req = {
        "days": None,
        "people": None,
        "budget": None,
        "type": None,
        "season": None,
        "location": None,
    }

    # 天数
    day_match = re.search(r"(\d+)晚(\d+)天|(\d+)天(\d+)晚|(\d+)天", query)
    if day_match:
        for g in day_match.groups():
            if g:
                if day_match.group(0).count("晚") > 0:
                    req["days"] = int(g) + 1
                else:
                    req["days"] = int(g)

    # 人数
    people_match = re.search(r"(\d+)人", query)
    if people_match:
        req["people"] = int(people_match.group(1))
    elif any(kw in query for kw in ["一家", "亲子", "家庭", "带小孩"]):
        req["people"] = "family"

    # 类型
    if any(kw in query for kw in ["主题团", "拼团"]):
        req["type"] = "主题团"
    elif any(kw in query for kw in ["私享", "管家", "定制"]):
        req["type"] = "私享管家"
    elif "自由行" in query:
        req["type"] = "自由行"

    # 季节/主题
    if any(kw in query for kw in ["桃花", "春天", "春季"]):
        req["season"] = "桃花季"
    elif any(kw in query for kw in ["亲子", "小朋友", "小孩"]):
        req["season"] = "亲子"
    elif any(kw in query for kw in ["杜鹃", "夏季"]):
        req["season"] = "杜鹃季"

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

    # 标签匹配（20种标签，含模糊匹配）
    tag_map = {
        "主题团": ["主题团"],
        "私享管家": ["私享管家"],
        "自由行": ["自由行"],
        "亲子度假": ["亲子度假", "亲子"],
        "亲子研学": ["亲子研学", "亲子"],
        "深度户外": ["深度户外", "户外", "徒步"],
        "轻户外": ["轻户外", "户外", "徒步"],
        "深度文化体验": ["深度文化体验", "文化"],
        "自然景观": ["自然景观", "风景"],
        "低空旅行": ["低空旅行", "直升机", "低空"],
        "高原花季": ["高原花季", "桃花", "杜鹃", "花季", "赏花"],
        "美食美酒": ["美食美酒", "美食", "美酒", "品酒"],
        "度假休闲": ["度假休闲", "度假", "休闲"],
        "疗愈": ["疗愈", "放松", "康养"],
        "自然博物": ["自然博物", "博物", "自然教育"],
        "摄影爱好": ["摄影爱好", "摄影"],
        "低海拔": ["低海拔"],
        "银发出行": ["银发出行", "老人", "银发", "老年人"],
        "寻找珍贵风物": ["寻找珍贵风物", "风物", "物产"],
        "目的地套餐": ["目的地套餐", "套餐"],
    }
    for tag, keywords in tag_map.items():
        if any(kw in query for kw in keywords):
            req["tag"] = tag
            break

    return req


def score_product(product: dict, req: dict) -> float:
    """计算产品与需求的匹配分数"""
    meta = product.get("metadata", {})
    score = 1.0
    reasons = []

    if req.get("days") and meta.get("itinerary_days"):
        diff = abs(req["days"] - meta.get("itinerary_days", 0))
        if diff == 0:
            score += 0.5
            reasons.append("天数完全匹配")
        elif diff <= 1:
            score += 0.2
            reasons.append("天数相近")

    if req.get("type") and meta.get("category_sub"):
        if req["type"] in meta.get("category_sub", ""):
            score += 0.3
            reasons.append(f"产品类型匹配({meta.get('category_sub')})")

    if req.get("season"):
        tags = meta.get("tags", "")
        if req["season"] in tags:
            score += 0.3
            reasons.append(f"符合{req['season']}主题")

    if req.get("location"):
        title = meta.get("title", "")
        series = meta.get("series", "")
        if req["location"] in title or req["location"] in series:
            score += 0.4
            reasons.append(f"目的地在{req['location']}")

    # 标签精准匹配（权重最高）
    if req.get("tag"):
        product_tags = meta.get("tags", "")
        if req["tag"] in product_tags:
            score += 2.0
            reasons.append(f"标签匹配: {req['tag']}")

    product["score"] = score
    product["reasons"] = reasons
    return score


def format_product(product: dict) -> str:
    """格式化产品输出"""
    meta = product.get("metadata", {})
    reasons = product.get("reasons", [])

    lines = [
        f"\n{'='*50}",
        f"【{meta.get('title', '未知产品')}】",
        f"{'='*50}",
        f"📍 产品ID: {meta.get('travel_type', '')}",
        f"🏷️ 环线: {meta.get('series', '')}",
        f"📅 行程: {meta.get('itinerary_days', 0)}天{meta.get('itinerary_nights', 0)}晚",
        f"🚗 类型: {meta.get('category_sub', '')}",
        f"📍 集合: {meta.get('rendezvous', '')} → 散团: {meta.get('dissolution', '')}",
    ]

    if meta.get("tags"):
        lines.append(f"🏷️ 标签: {meta.get('tags')}")

    if reasons:
        lines.append(f"✅ 推荐理由: {'; '.join(reasons)}")

    lines.append(f"📊 相关度: {1 - product.get('distance', 1):.2%}")

    return "\n".join(lines)


def recommend(query: str, top_k: int = 5) -> list:
    """主推荐函数"""
    print(f"\n🎯 用户需求: {query}")

    req = parse_requirements(query)
    print(f"📋 解析需求: {json.dumps(req, ensure_ascii=False)}")

    products = query_vectorstore(query, n_results=100)

    if not products:
        return []

    for p in products:
        score_product(p, req)

    # 综合排序：规则分数 + 语义相关度（距离越小越好，权重0.01）
    products.sort(key=lambda x: x["score"] + abs(x.get("distance", 0)) * 0.01, reverse=True)
    return products[:top_k]


def main():
    parser = argparse.ArgumentParser(description="松赞旅行产品推荐助手")
    parser.add_argument("query", nargs="*", help="查询内容")
    parser.add_argument("-k", "--top", type=int, default=5, help="返回结果数量")
    args = parser.parse_args()

    if not args.query:
        print("""
╔══════════════════════════════════════════════════╗
║       欢迎使用松赞旅行产品推荐助手               ║
╠══════════════════════════════════════════════════╣
║  请输入您的旅行需求，如：                        ║
║  - "适合亲子的5天产品"                           ║
║  - "波密地区的主题团"                            ║
║  - "2大1小，桃花节去林芝"                        ║
║  - "私享管家，6天5晚"                            ║
║  输入 q 退出                                     ║
╚══════════════════════════════════════════════════╝
""")
        while True:
            q = input("\n请输入您的需求: ").strip()
            if q.lower() in ["q", "quit", "exit"]:
                break
            if not q:
                continue

            results = recommend(q, top_k=args.top)
            if results:
                print(f"\n🌟 为您找到 {len(results)} 个推荐产品:")
                for i, p in enumerate(results, 1):
                    print(f"\n{i}.", end="")
                    print(format_product(p))
            else:
                print("未找到匹配的产品")
            print()
    else:
        query_text = " ".join(args.query)
        results = recommend(query_text, top_k=args.top)
        if results:
            print(f"\n🌟 为您找到 {len(results)} 个推荐产品:")
            for i, p in enumerate(results, 1):
                print(f"\n{i}.", end="")
                print(format_product(p))
        else:
            print("未找到匹配的产品")


if __name__ == "__main__":
    main()
