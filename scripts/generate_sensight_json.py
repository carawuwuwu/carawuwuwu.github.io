#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from zoneinfo import ZoneInfo

import requests

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "sensight.json"
SH_TZ = ZoneInfo("Asia/Shanghai")
BASE_SENSIGHT = "https://sensight.bytedance.net"
SKILL_VERSION = "0.3.2"
CLIENT_ID_FILE = Path.home() / ".sensight" / ".sensight_client_id"

EVENT_QUERY = "618 电商 直播 优惠 券后价 国补 品牌"
SOCIAL_QUERY = "618 直播间 优惠券 到手价 国补"
PAIN_QUERY = "618 规则复杂 买贵 凑单 领券"
BRAND_WATCHLIST = [
    {"brand": "京东", "platform": 3, "author_name": "京东", "industry": "tech"},
    {"brand": "天猫", "platform": 3, "author_name": "天猫", "industry": "fashion"},
    {"brand": "小米公司", "platform": 3, "author_name": "小米公司", "industry": "tech"},
    {"brand": "海尔", "platform": 3, "author_name": "海尔", "industry": "tech"},
]

SIGNAL_KEYWORDS = [
    "直播间",
    "直播",
    "优惠券",
    "直播券",
    "到手价",
    "券后价",
    "大额券",
    "叠券",
    "满减",
    "国补",
    "补贴",
    "以旧换新",
    "囤货",
    "攻略",
    "返场",
    "专场",
]
PAIN_KEYWORDS = ["复杂", "看不懂", "不会", "买贵", "凑单", "错过", "来不及", "怕", "拖", "懒"]
INDUSTRY_KEYWORDS = {
    "fashion": ["防晒衣", "穿搭", "连衣裙", "凉感", "显瘦", "通勤", "服饰", "鞋"],
    "beauty": ["防晒", "底妆", "粉底", "持妆", "精华", "修护", "美妆", "口红"],
    "food": ["零食", "饮品", "低糖", "囤货", "酸奶", "咖啡", "轻食", "椰子水"],
    "tech": ["国补", "补贴", "手机", "家电", "平板", "空调", "耳机", "清洁电器", "奔驰", "汽车"],
    "daily": ["洗衣液", "纸巾", "驱蚊", "除菌", "清洁", "大包装", "留香", "家庭装"],
    "baby": ["宝宝", "母婴", "纸尿裤", "湿巾", "婴儿", "妈妈", "新手妈妈"],
    "edu": ["学习机", "课程", "暑期", "家长", "试听", "AI工具", "升学", "规划"],
}
PLATFORM_MAP = {
    "xiaohongshu.com": "小红书",
    "weibo.com": "微博",
    "m.weibo.cn": "微博",
    "mp.weixin.qq.com": "公众号",
    "x.com": "X",
    "twitter.com": "X",
}
INDUSTRY_TEMPLATE = {
    "fashion": {
        "summary": "服饰今天更适合把直播权益和上身场景一起讲，别只报低价。",
        "hot_words": ["直播间券", "到手价", "凉感穿搭", "上身实拍"],
        "content_angles": ["先拍通勤 / 出游上身效果，再补券后价", "把尺码、版型、显瘦点讲具体", "标题里直接写清直播间权益"],
        "pain_points": ["用户担心买贵", "怕只讲价格不讲上身差异"],
        "recommended_action": "优先推防晒衣、凉感通勤、约会出游等可视化强的单品。",
    },
    "beauty": {
        "summary": "美妆今天适合走“真实效果 + 券后价”双线，不要只讲成分。",
        "hot_words": ["防晒", "高温持妆", "券后到手", "上脸实测"],
        "content_angles": ["优先做暴晒 / 持妆 / 上脸实测", "直播把肤质、色号、肤感说透", "把券后价与赠品组合一起展示"],
        "pain_points": ["用户担心踩雷", "只报折扣但不讲肤感说服力不够"],
        "recommended_action": "优先推防晒、底妆、修护精华等有明显场景和实测空间的品类。",
    },
    "food": {
        "summary": "食饮今天更适合放大囤货理由和即时满足感，把直播福利说得直接一点。",
        "hot_words": ["囤货", "直播福利", "低糖", "办公室补能"],
        "content_angles": ["从办公室、熬夜、夏季补水场景切入", "强调整箱 / 组合装更划算", "用懒人囤货清单形式更容易转发"],
        "pain_points": ["用户担心优惠规则太绕", "怕买多了不划算"],
        "recommended_action": "优先推饮品、轻食和高频囤货型零食。",
    },
    "tech": {
        "summary": "3C 今天最值得放大的仍然是国补、以旧换新和直播专场福利。",
        "hot_words": ["国补", "补贴", "以旧换新", "直播专场"],
        "content_angles": ["第一句话先报补贴后到手价", "把怎么领补贴、怎么换新讲成步骤", "高客单一定要补真实体验和版本建议"],
        "pain_points": ["用户最怕政策没讲清楚", "高客单只讲价格不讲体验会犹豫"],
        "recommended_action": "优先推手机 / 平板、家电、清洁电器等能接补贴话题的品类。",
    },
    "daily": {
        "summary": "日化今天适合继续走家庭囤货路线，把大包装和单次成本讲明白。",
        "hot_words": ["家庭装", "囤货", "满减", "留香 / 去污实测"],
        "content_angles": ["多拍前后效果差和使用成本", "直播突出满减和赠品", "适合懒人囤货攻略模板"],
        "pain_points": ["用户担心囤太多不划算", "看不到实际效果时转化会掉"],
        "recommended_action": "优先推洗护清洁、纸品和驱蚊除菌。",
    },
    "baby": {
        "summary": "母婴今天更需要把安全感讲透，再叠加福利表达。",
        "hot_words": ["妈妈囤货", "安心成分", "整夜安睡", "夏季护理"],
        "content_angles": ["先回答会不会刺激 / 漏不漏 / 能不能安心用", "用真实演示建立信任", "券后价只做辅助，不要喧宾夺主"],
        "pain_points": ["母婴人群对安全成分更敏感", "直播只讲便宜不够建立信任"],
        "recommended_action": "优先推纸尿裤、夏季护理和喂养 / 安全大件。",
    },
    "edu": {
        "summary": "教育今天更适合走暑期规划和家庭决策逻辑，内容要更像顾问建议。",
        "hot_words": ["暑期规划", "试听", "家长决策", "AI 学习工具"],
        "content_angles": ["先讲时间窗口和掉队焦虑", "再给试听 / 资料包 / 使用演示", "把报名优惠和顾问答疑串起来"],
        "pain_points": ["家长怕踩坑", "只讲优惠不讲效果很难留资"],
        "recommended_action": "优先推暑期课程、学习机 / AI 工具和规划咨询。",
    },
}


def now_sh() -> datetime:
    return datetime.now(SH_TZ)


def get_client_id() -> str:
    if CLIENT_ID_FILE.exists():
        return CLIENT_ID_FILE.read_text(encoding="utf-8").strip()
    CLIENT_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    client_id = str(uuid.uuid4())
    CLIENT_ID_FILE.write_text(client_id, encoding="utf-8")
    return client_id


def build_headers(action: str) -> Dict[str, str]:
    return {
        "Content-Type": "application/json",
        "x-skill-version": SKILL_VERSION,
        "x-skill-action": action,
        "x-skill-client-id": get_client_id(),
    }


def post_json(url: str, payload: Dict[str, Any], action: str, timeout: int = 30) -> Dict[str, Any]:
    resp = requests.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=build_headers(action), timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def auth_email(email: str) -> None:
    requests.post(
        f"{BASE_SENSIGHT}/sensight/skill_user_auth",
        data=json.dumps({"client_id": get_client_id(), "auth_id": email, "auth_type": "email"}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        timeout=15,
    ).raise_for_status()


def safe_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_text(value: Any, limit: int = 110) -> str:
    text = safe_text(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def platform_from_url(url: str) -> str:
    for key, label in PLATFORM_MAP.items():
        if key in (url or ""):
            return label
    return "社媒"


def unique_keep_order(items: List[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def count_keywords(texts: List[str], keywords: List[str]) -> Counter:
    joined = "\n".join(texts)
    counter: Counter = Counter()
    for keyword in keywords:
        counter[keyword] = joined.count(keyword)
    return Counter({k: v for k, v in counter.items() if v > 0})


def industry_rank(texts: List[str]) -> List[str]:
    scores = {}
    joined = "\n".join(texts)
    for industry, words in INDUSTRY_KEYWORDS.items():
        scores[industry] = sum(joined.count(word) for word in words)
    ordered = [k for k, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True) if scores[k] > 0]
    if not ordered:
        return ["tech", "beauty", "fashion"]
    return ordered


def infer_tag(text: str) -> str:
    if "国补" in text or "补贴" in text:
        return "补贴"
    if "攻略" in text or "怎么领" in text or "步骤" in text:
        return "攻略"
    if "复杂" in text or "买贵" in text or "凑单" in text:
        return "痛点"
    if "直播" in text or "优惠券" in text or "到手价" in text:
        return "权益"
    return "观察"


def infer_industries(text: str) -> List[str]:
    hits = []
    for industry, keywords in INDUSTRY_KEYWORDS.items():
        if any(word in text for word in keywords):
            hits.append(industry)
    if not hits:
        return ["tech"] if any(word in text for word in ["国补", "补贴", "家电", "手机"]) else []
    return hits[:2]


def build_header(signal_counts: Counter, pain_counts: Counter, top_industries: List[str]) -> Dict[str, str]:
    lead = [item[0] for item in signal_counts.most_common(2)] or ["直播权益", "到手价"]
    pain = pain_counts.most_common(1)[0][0] if pain_counts else "规则理解"
    industry_map = {
        "fashion": "服饰",
        "beauty": "美妆",
        "food": "食饮",
        "tech": "3C / 家电",
        "daily": "日化",
        "baby": "母婴",
        "edu": "教育",
    }
    top_industry_text = " / ".join(industry_map.get(x, x) for x in top_industries[:2])
    return {
        "trend_title": f"{lead[0]} + {lead[1]} 成为主驱动" if len(lead) > 1 else f"{lead[0]} 成为主驱动",
        "trend_desc": "社媒讨论更偏向直播权益、补贴说明和到手价表达。",
        "recommend_title": "先讲怎么领，再讲多便宜",
        "recommend_desc": f"今天最大的转化阻力仍是“{pain}”相关理解成本，建议把规则说明前置。",
        "industry_focus": top_industry_text or "3C / 家电",
        "industry_desc": "优先把最能接权益和补贴的行业先推起来，再补情绪和种草内容。",
    }


def build_today_signals(signal_counts: Counter, pain_counts: Counter, top_industries: List[str], brand_watch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lead = [item[0] for item in signal_counts.most_common(3)] or ["直播间券", "到手价", "国补"]
    pain = [item[0] for item in pain_counts.most_common(2)] or ["规则复杂", "买贵"]
    industry_label = {
        "fashion": "服饰",
        "beauty": "美妆",
        "food": "食饮",
        "tech": "3C / 家电",
        "daily": "日化",
        "baby": "母婴",
        "edu": "教育",
    }
    top_text = " / ".join(industry_label.get(x, x) for x in top_industries[:3])
    brand_line = "；".join(item["summary"] for item in brand_watch[:2]) if brand_watch else "品牌官号内容也在持续把直播权益前置。"
    return [
        {
            "title": "权益型表达明显升温",
            "summary": f"今天高频出现 {lead[0]}、{lead[1]}、{lead[2]}，说明用户更吃“直接告诉我能省多少钱”。",
            "evidence": "适合把券后价、补贴和直播专场写在封面第一屏。",
            "priority": "high",
        },
        {
            "title": "规则说明就是转化门槛",
            "summary": f"围绕 {pain[0]}、{pain[1]} 的吐槽仍在，用户不是不想买，而是怕规则绕、怕买贵。",
            "evidence": "建议把“怎么领、怎么叠、怎么补”做成懒人版步骤。",
            "priority": "high",
        },
        {
            "title": "今天优先推能接权益的行业",
            "summary": f"从当前社媒和品牌动作看，{top_text} 更容易承接直播权益、补贴和价格型表达。",
            "evidence": "晨会可先把这些行业排在前面，再补纯情绪型话题。",
            "priority": "medium",
        },
        {
            "title": "内容打法更适合攻略化",
            "summary": brand_line,
            "evidence": "今天不是只报低价，而是把入口、场景和利益点串成一步一步可照做的话术。",
            "priority": "medium",
        },
    ]


def summarize_feature_reason(text: str) -> str:
    if "直播间" in text and ("优惠券" in text or "补贴" in text):
        return "把直播间专属权益讲得很具体，用户一眼能看懂值不值。"
    if "国补" in text or "补贴" in text:
        return "补贴信息直接对应高价决策，天然适合做转化解释。"
    if "攻略" in text or "领券" in text:
        return "它把复杂的优惠路径讲成了懒人攻略，转发价值高。"
    return "内容把利益点、场景和动作链路串在了一起，适合做模板参考。"


def summarize_feature_hook(text: str) -> str:
    if "直播间" in text and "优惠券" in text:
        return "先抛出直播间专属券，再补具体领取步骤。"
    if "国补" in text or "补贴" in text:
        return "第一句话就报补贴后到手价。"
    if "攻略" in text or "领券" in text:
        return "用‘别错过 / 一步到位 / 懒人版’这类低门槛话术。"
    return "封面先给利益点，正文再补规则和场景。"


def build_social_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for item in items[:6]:
        merged_text = safe_text(item.get("title") or item.get("content")) + " " + safe_text(item.get("content"))
        result.append(
            {
                "platform": platform_from_url(item.get("url", "")),
                "user_name": item.get("user_name") or "匿名用户",
                "title": safe_text(item.get("title")) or short_text(item.get("content"), 28),
                "publish_time": item.get("publish_time") or "",
                "score": item.get("score") or 0,
                "url": item.get("url") or "#",
                "snippet": short_text(item.get("content"), 120),
                "tag": infer_tag(merged_text),
                "industries": infer_industries(merged_text),
            }
        )
    return result


def merge_social_results(primary: List[Dict[str, Any]], pain: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen = set()
    for item in primary + pain:
        url = item.get("url") or ""
        key = url or (item.get("user_name"), item.get("title"), item.get("publish_time"))
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    merged.sort(key=lambda x: float(x.get("score") or 0), reverse=True)
    return merged


def build_featured_posts(base_items: List[Dict[str, Any]], link_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    detailed_by_title = {safe_text(item.get("title") or item.get("content")): item for item in link_items}
    result = []
    for item in base_items[:3]:
        lookup_key = safe_text(item.get("title") or item.get("content"))
        detail = detailed_by_title.get(lookup_key) or {}
        content = safe_text(detail.get("content") or item.get("content"))
        result.append(
            {
                "platform": platform_from_url(item.get("url", "")),
                "title": safe_text(item.get("title")) or short_text(content, 24),
                "user_name": item.get("user_name") or detail.get("user_name") or "作者",
                "publish_time": detail.get("publish_time") or item.get("publish_time") or "",
                "url": item.get("url") or "#",
                "summary": short_text(content, 150),
                "why_hot": summarize_feature_reason(content),
                "hook": summarize_feature_hook(content),
                "tag": infer_tag(content),
            }
        )
    return result


def build_brand_watch(author_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    result = []
    for author in author_results:
        items = author.get("items") or []
        if not items:
            continue
        latest = items[0]
        text = safe_text(latest.get("content"))
        summary = short_text(text, 90)
        if "直播" in text:
            insight = "最近动作更偏直播专场 / 直播福利。"
        elif "补贴" in text or "国补" in text:
            insight = "最近动作明显在放大补贴和到手价。"
        else:
            insight = "最近动作更偏品牌活动造势和节点预热。"
        result.append(
            {
                "brand": author.get("selected_author_name") or author.get("author_name") or "品牌",
                "platform": "微博",
                "summary": f"{author.get('selected_author_name') or author.get('author_name')}：{summary}",
                "insight": insight,
                "recent_posts": [
                    {
                        "title": short_text(item.get("title") or item.get("content"), 36),
                        "publish_time": item.get("publish_time") or "",
                        "url": item.get("url") or "#",
                    }
                    for item in items[:2]
                ],
            }
        )
    return result


def build_industry_overrides(top_industries: List[str], signal_counts: Counter) -> Dict[str, Any]:
    top_signals = [item[0] for item in signal_counts.most_common(3)] or ["直播间券", "到手价", "国补"]
    overrides = {}
    for industry, template in INDUSTRY_TEMPLATE.items():
        hot_words = unique_keep_order(template["hot_words"] + top_signals)
        summary = template["summary"]
        if industry == top_industries[0]:
            summary = "今天这一行最适合优先开工：" + summary
        overrides[industry] = {
            "summary": summary,
            "hot_words": hot_words[:6],
            "content_angles": template["content_angles"][:3],
            "pain_points": template["pain_points"][:2],
            "recommended_action": template["recommended_action"],
        }
    return overrides


def load_existing() -> Dict[str, Any]:
    if DATA_PATH.exists():
        return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate data/sensight.json for the 618 dashboard")
    parser.add_argument("--auth-email", help="Email for Sensight auth. Fallback to SENSIGHT_AUTH_EMAIL or AIME_CURRENT_USER_EMAIL")
    parser.add_argument("--allow-stale-fallback", action="store_true", help="Reuse existing sensight.json when remote fetch fails")
    args = parser.parse_args()

    notes: List[str] = []
    errors: List[str] = []
    existing = load_existing()
    now = now_sh()
    email = args.auth_email or os.getenv("SENSIGHT_AUTH_EMAIL") or os.getenv("AIME_CURRENT_USER_EMAIL")

    if email:
        try:
            auth_email(email)
            notes.append("已完成 Sensight email 鉴权。")
        except Exception as exc:
            errors.append(f"鉴权失败：{exc}")
    else:
        notes.append("未提供 SENSIGHT_AUTH_EMAIL；自动化环境若无已绑定 client_id，可能沿用上次生成的数据。")

    event_items: List[Dict[str, Any]] = []
    social_items: List[Dict[str, Any]] = []
    pain_items: List[Dict[str, Any]] = []
    brand_raw: List[Dict[str, Any]] = []
    link_items: List[Dict[str, Any]] = []

    try:
        event_items = (post_json(f"{BASE_SENSIGHT}/sensight/skill_search_events", {"query": EVENT_QUERY}, "search_events").get("items") or [])[:12]
    except Exception as exc:
        errors.append(f"search_events 失败：{exc}")

    try:
        social_items = (post_json(f"{BASE_SENSIGHT}/sensight/skill_social_search", {"query": SOCIAL_QUERY, "platforms": [2, 3], "size": 12}, "social_search").get("items") or [])[:12]
    except Exception as exc:
        errors.append(f"social_search 主查询失败：{exc}")

    try:
        pain_items = (post_json(f"{BASE_SENSIGHT}/sensight/skill_social_search", {"query": PAIN_QUERY, "platforms": [2, 3], "size": 8}, "social_search").get("items") or [])[:8]
    except Exception as exc:
        errors.append(f"social_search 痛点查询失败：{exc}")

    for watch in BRAND_WATCHLIST:
        try:
            payload = {
                "platform": watch["platform"],
                "author_name": watch["author_name"],
                "size": 3,
                "page_number": 1,
            }
            result = post_json(f"{BASE_SENSIGHT}/sensight/skill_search_author_posts", payload, "search_author_posts")
            result["author_name"] = watch["author_name"]
            brand_raw.append(result)
        except Exception as exc:
            errors.append(f"品牌观察 {watch['author_name']} 失败：{exc}")

    merged_social = merge_social_results(social_items, pain_items)
    top_urls = [item.get("url") for item in merged_social[:3] if item.get("url")]
    if top_urls:
        try:
            link_items = post_json(f"{BASE_SENSIGHT}/sensight/skill_social_link_search", {"urls": top_urls}, "social_link_search").get("items") or []
        except Exception as exc:
            errors.append(f"social_link_search 失败：{exc}")

    texts = [safe_text(item.get("title")) + " " + safe_text(item.get("summary")) for item in event_items]
    texts += [safe_text(item.get("title")) + " " + safe_text(item.get("content")) for item in merged_social]
    texts += [safe_text((item.get("items") or [{}])[0].get("content")) for item in brand_raw if item.get("items")]

    if not any(texts) and existing and args.allow_stale_fallback:
        print("No fresh Sensight data, keep existing data/sensight.json", file=sys.stderr)
        return

    signal_counts = count_keywords(texts, SIGNAL_KEYWORDS)
    pain_counts = count_keywords(texts, PAIN_KEYWORDS)
    top_industries = industry_rank(texts)
    social_cards = build_social_items(merged_social)
    brand_watch = build_brand_watch(brand_raw)
    featured_posts = build_featured_posts(merged_social, link_items)
    header = build_header(signal_counts, pain_counts, top_industries)
    today_signals = build_today_signals(signal_counts, pain_counts, top_industries, brand_watch)
    industry_overrides = build_industry_overrides(top_industries, signal_counts)

    positive_keywords = [item[0] for item in signal_counts.most_common(5)] or ["直播间券", "到手价", "国补"]
    pain_keywords = [item[0] for item in pain_counts.most_common(4)] or ["规则复杂", "买贵"]
    content_hooks = unique_keep_order([
        "懒人领券攻略",
        "直播间专属券前置",
        "补贴 / 国补说明",
        "到手价一步讲清",
    ])

    data = {
        "meta": {
            "version": 1,
            "timezone": "Asia/Shanghai",
            "generated_at": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_at_local": now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "generated_date": now.strftime("%Y-%m-%d"),
            "generator": "scripts/generate_sensight_json.py",
            "status": "partial" if errors else "success",
            "notes": notes,
            "errors": errors,
        },
        "header": header,
        "today_signals": today_signals,
        "social_observations": {
            "summary": "社媒讨论的重心集中在直播权益、补贴说明、到手价和懒人攻略。",
            "positive_keywords": positive_keywords,
            "pain_points": pain_keywords,
            "content_hooks": content_hooks,
            "items": social_cards,
        },
        "featured_posts": featured_posts,
        "brand_watch": brand_watch,
        "industry_overrides": industry_overrides,
        "event_brief": [
            {
                "title": safe_text(item.get("title")),
                "source": item.get("ranking_name") or "热点事件",
                "summary": short_text(item.get("summary") or item.get("title"), 90),
                "url": item.get("url") or "#",
            }
            for item in event_items[:6]
            if safe_text(item.get("title"))
        ],
    }

    DATA_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {DATA_PATH}")


if __name__ == "__main__":
    main()
