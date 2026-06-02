#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "hot.json"
SH_TZ = ZoneInfo("Asia/Shanghai")

TOPHUB_HOME_URL = "https://tophub.today/"
DOUYIN_API_URL = "https://test12345-eta.vercel.app/douyin"
REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/136.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "text/html,application/json;q=0.9,*/*;q=0.8",
}

HOT_SPECS = [
    {
        "key": "douyin",
        "section": "hot",
        "name": "抖音",
        "en": "Douyin",
        "title": "实时热榜",
        "source_kind": "api",
        "primary_url": DOUYIN_API_URL,
        "fallback_hashid": "DpQvNABoNE",
        "fallback_name": "TopHub 抖音总榜",
    },
    {
        "key": "weibo",
        "section": "hot",
        "name": "微博",
        "en": "Weibo",
        "title": "热搜榜",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/KqndgxeLl9",
        "hashid": "KqndgxeLl9",
        "source_name": "TopHub 微博热搜榜",
    },
    {
        "key": "baidu",
        "section": "hot",
        "name": "百度",
        "en": "Baidu",
        "title": "实时热点",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/Jb0vmloB1G",
        "hashid": "Jb0vmloB1G",
        "source_name": "TopHub 百度实时热点",
    },
    {
        "key": "kuaishou",
        "section": "hot",
        "name": "快手",
        "en": "Kuaishou",
        "title": "实时热榜",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/MZd7PrPerO",
        "hashid": "MZd7PrPerO",
        "source_name": "TopHub 快手实时热榜",
    },
]

PRODUCT_SPECS = [
    {
        "key": "tmall",
        "section": "products",
        "name": "淘宝天猫",
        "en": "Tmall",
        "title": "热销总榜",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/yjvQDpjobg",
        "hashid": "yjvQDpjobg",
        "source_name": "TopHub 淘宝天猫热销总榜",
    },
    {
        "key": "jd",
        "section": "products",
        "name": "京东",
        "en": "JD",
        "title": "热销总榜",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/YqoXzV6dOD",
        "hashid": "YqoXzV6dOD",
        "source_name": "TopHub 京东热销总榜",
    },
    {
        "key": "remai",
        "section": "products",
        "name": "今日热卖",
        "en": "Today Best Sellers",
        "title": "全网线报聚合",
        "source_kind": "web",
        "primary_url": "https://tophub.today/n/x9ozqX7eXb",
        "hashid": "x9ozqX7eXb",
        "source_name": "TopHub 今日热卖全网线报聚合",
    },
    {
        "key": "kuaishou_shop",
        "section": "products",
        "name": "快手电商",
        "en": "Kuaishou Shop",
        "title": "热卖榜",
        "source_kind": "web",
        "primary_url": "https://tophub.today/",
        "hashid": None,
        "source_name": "快手电商公开榜单",
        "optional": True,
    },
]

SPEC_MAP = {spec["key"]: spec for spec in [*HOT_SPECS, *PRODUCT_SPECS]}


class FetchError(RuntimeError):
    pass


def now_context() -> Dict[str, str]:
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(SH_TZ)
    return {
        "iso_utc": now_utc.replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "iso_local": now_local.isoformat(timespec="seconds"),
        "display_local": now_local.strftime("%Y-%m-%d %H:%M:%S CST"),
        "date_local": now_local.strftime("%Y-%m-%d"),
    }


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def read_existing(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def clean_text(value: Optional[str]) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value).strip()


def first_text(node, selector: str) -> str:
    if node is None:
        return ""
    target = node.select_one(selector)
    return clean_text(target.get_text(" ", strip=True)) if target else ""


def fetch_tophub_home(session: requests.Session) -> BeautifulSoup:
    response = session.get(TOPHUB_HOME_URL, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def parse_rank(rank_text: str, fallback_rank: int) -> int:
    matched = re.search(r"\d+", rank_text or "")
    return int(matched.group()) if matched else fallback_rank


def parse_tophub_card(soup: BeautifulSoup, hashid: str, top_n: int = 10) -> Dict[str, Any]:
    marker = soup.select_one(f'div.i-o[hashid="{hashid}"]')
    if marker is None:
        raise FetchError(f"TopHub 首页中未找到节点 {hashid}")

    card = marker.find_parent("div", class_="cc-cd")
    if card is None:
        raise FetchError(f"节点 {hashid} 缺少榜单卡片容器")

    platform_name = first_text(card, ".cc-cd-lb span")
    board_title = first_text(card, ".cc-cd-sb-st")
    updated_text = first_text(card, ".i-h")

    items: List[Dict[str, Any]] = []
    for index, anchor in enumerate(card.select(".cc-cd-cb-l > a"), start=1):
        title = first_text(anchor, ".t")
        if not title:
            continue
        rank = parse_rank(first_text(anchor, ".s"), index)
        metric_text = first_text(anchor, ".e")
        items.append(
            {
                "rank": rank,
                "title": title,
                "url": anchor.get("href") or "",
                "metric_text": metric_text,
                "subtitle": metric_text,
                "source_rank": rank,
            }
        )
        if len(items) >= top_n:
            break

    if len(items) < 1:
        raise FetchError(f"节点 {hashid} 未解析到榜单条目")

    items.sort(key=lambda item: item.get("rank", 0))
    return {
        "platform_name": platform_name,
        "board_title": board_title,
        "updated_text": updated_text,
        "items": items,
    }


def fetch_douyin_api(session: requests.Session, top_n: int = 10) -> Dict[str, Any]:
    response = session.get(DOUYIN_API_URL, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 200:
        raise FetchError(f"抖音接口返回异常 code={payload.get('code')}")
    raw_items = payload.get("data") or []
    items = []
    for index, item in enumerate(raw_items[:top_n], start=1):
        title = clean_text(item.get("title") or item.get("word") or item.get("keyword"))
        if not title:
            continue
        hot_value = item.get("hot") or item.get("score") or item.get("value")
        metric_text = f"{hot_value:,}" if isinstance(hot_value, int) else clean_text(str(hot_value or ""))
        items.append(
            {
                "rank": index,
                "title": title,
                "url": item.get("url") or item.get("mobileUrl") or payload.get("link") or "",
                "metric_text": metric_text,
                "metric_value": hot_value,
                "subtitle": payload.get("description") or payload.get("type") or "",
                "source_rank": index,
            }
        )
    if len(items) < 1:
        raise FetchError("抖音接口未返回可用榜单数据")
    return {
        "platform_name": clean_text(payload.get("title") or "抖音"),
        "board_title": clean_text(payload.get("type") or "热榜"),
        "updated_text": clean_text(payload.get("updateTime")),
        "items": items,
        "link": payload.get("link") or DOUYIN_API_URL,
        "description": clean_text(payload.get("description")),
        "from_cache": bool(payload.get("fromCache")),
    }


def build_platform_payload(
    spec: Dict[str, Any],
    *,
    context: Dict[str, str],
    source_name: str,
    source_url: str,
    source_kind: str,
    updated_at: str,
    items: List[Dict[str, Any]],
    status: str = "fresh",
    status_text: str = "今日已更新",
    stale: bool = False,
    fallback: Optional[Dict[str, Any]] = None,
    note: str = "",
) -> Dict[str, Any]:
    return {
        "key": spec["key"],
        "section": spec["section"],
        "name": spec["name"],
        "en": spec["en"],
        "title": spec["title"],
        "status": status,
        "status_text": status_text,
        "stale": stale,
        "fallback": fallback,
        "note": note,
        "source_kind": source_kind,
        "source_name": source_name,
        "source_url": source_url,
        "updated_at": updated_at,
        "generated_at": context["iso_utc"],
        "item_count": len(items),
        "items": items,
    }


def build_meta_entry(platform_payload: Dict[str, Any], reason: str = "") -> Dict[str, Any]:
    return {
        "section": platform_payload.get("section"),
        "name": platform_payload.get("name"),
        "status": platform_payload.get("status"),
        "status_text": platform_payload.get("status_text"),
        "stale": platform_payload.get("stale", False),
        "fallback": platform_payload.get("fallback"),
        "source_kind": platform_payload.get("source_kind"),
        "source_name": platform_payload.get("source_name"),
        "source_url": platform_payload.get("source_url"),
        "updated_at": platform_payload.get("updated_at"),
        "item_count": platform_payload.get("item_count", 0),
        "note": platform_payload.get("note", ""),
        "reason": reason,
    }


def stale_from_existing(
    spec: Dict[str, Any],
    existing_root: Dict[str, Any],
    context: Dict[str, str],
    reason: str,
) -> Optional[Dict[str, Any]]:
    existing_section = existing_root.get(spec["section"], {})
    existing_platform = existing_section.get(spec["key"])
    if not existing_platform:
        return None

    carried = copy.deepcopy(existing_platform)
    carried["section"] = spec["section"]
    carried["status"] = "stale"
    carried["status_text"] = "沿用上次数据"
    carried["stale"] = True
    carried["generated_at"] = context["iso_utc"]
    carried["fallback"] = {
        "type": "previous_data",
        "reason": reason,
        "from_generated_at": existing_platform.get("generated_at") or existing_platform.get("updated_at") or "",
    }
    old_note = clean_text(carried.get("note"))
    extra_note = f"本次抓取失败，已沿用仓库内上一版 {spec['name']} 数据。"
    carried["note"] = clean_text(f"{old_note} {extra_note}")
    return carried


def unavailable_platform(spec: Dict[str, Any], context: Dict[str, str], reason: str) -> Dict[str, Any]:
    return build_platform_payload(
        spec,
        context=context,
        source_name=spec.get("source_name") or spec["name"],
        source_url=spec.get("primary_url") or TOPHUB_HOME_URL,
        source_kind=spec.get("source_kind") or "web",
        updated_at="",
        items=[],
        status="unavailable",
        status_text="暂无更新",
        stale=False,
        fallback={"type": "none", "reason": reason},
        note=f"本次抓取失败，且仓库中暂无可沿用的历史数据：{reason}",
    )


def collect_data(existing_root: Dict[str, Any]) -> Dict[str, Any]:
    context = now_context()
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    meta_platforms: Dict[str, Any] = {}
    hot: Dict[str, Any] = {}
    products: Dict[str, Any] = {}

    soup: Optional[BeautifulSoup] = None
    tophub_home_error = ""

    try:
        soup = fetch_tophub_home(session)
    except Exception as exc:  # pragma: no cover - defensive
        tophub_home_error = str(exc)

    for spec in HOT_SPECS:
        platform_payload: Optional[Dict[str, Any]] = None
        failure_reason = ""
        try:
            if spec["key"] == "douyin":
                try:
                    api_data = fetch_douyin_api(session)
                    platform_payload = build_platform_payload(
                        spec,
                        context=context,
                        source_name="DailyHotApi /douyin",
                        source_url=DOUYIN_API_URL,
                        source_kind="api",
                        updated_at=api_data.get("updated_text") or context["display_local"],
                        items=api_data["items"],
                        note="优先使用 DailyHotApi 抖音热榜接口。",
                    )
                except Exception as api_exc:
                    failure_reason = f"DailyHotApi 抖音接口失败：{api_exc}"
                    if soup is not None and spec.get("fallback_hashid"):
                        fallback_data = parse_tophub_card(soup, spec["fallback_hashid"])
                        platform_payload = build_platform_payload(
                            spec,
                            context=context,
                            source_name=spec.get("fallback_name") or "TopHub 抖音总榜",
                            source_url=f"https://tophub.today/n/{spec['fallback_hashid']}",
                            source_kind="web_fallback",
                            updated_at=fallback_data.get("updated_text") or context["display_local"],
                            items=fallback_data["items"],
                            note=f"DailyHotApi 暂不可用，已改用 TopHub 抖音总榜补位。原因：{failure_reason}",
                        )
                    else:
                        raise FetchError(failure_reason)
            else:
                if soup is None:
                    raise FetchError(f"TopHub 首页抓取失败：{tophub_home_error or 'unknown error'}")
                card_data = parse_tophub_card(soup, spec["hashid"])
                platform_payload = build_platform_payload(
                    spec,
                    context=context,
                    source_name=spec.get("source_name") or spec["name"],
                    source_url=spec.get("primary_url") or TOPHUB_HOME_URL,
                    source_kind=spec.get("source_kind") or "web",
                    updated_at=card_data.get("updated_text") or context["display_local"],
                    items=card_data["items"],
                    note="数据来自 TopHub 首页公开榜单卡片。",
                )
        except Exception as exc:
            failure_reason = clean_text(str(exc)) or "抓取失败"

        if platform_payload is None:
            carried = stale_from_existing(spec, existing_root, context, failure_reason)
            platform_payload = carried or unavailable_platform(spec, context, failure_reason)
            meta_platforms[spec["key"]] = build_meta_entry(platform_payload, failure_reason)
        else:
            meta_platforms[spec["key"]] = build_meta_entry(platform_payload)
        hot[spec["key"]] = platform_payload

    for spec in PRODUCT_SPECS:
        platform_payload: Optional[Dict[str, Any]] = None
        failure_reason = ""
        try:
            if not spec.get("hashid"):
                raise FetchError("当前未接入稳定的快手电商公开榜单源")
            if soup is None:
                raise FetchError(f"TopHub 首页抓取失败：{tophub_home_error or 'unknown error'}")
            card_data = parse_tophub_card(soup, spec["hashid"])
            items = []
            for item in card_data["items"]:
                items.append(
                    {
                        "rank": item["rank"],
                        "title": item["title"],
                        "url": item.get("url", ""),
                        "metric_text": item.get("metric_text", ""),
                        "subtitle": item.get("subtitle", "") or "榜单信息待补充",
                        "source_rank": item.get("source_rank", item["rank"]),
                    }
                )
            platform_payload = build_platform_payload(
                spec,
                context=context,
                source_name=spec.get("source_name") or spec["name"],
                source_url=spec.get("primary_url") or TOPHUB_HOME_URL,
                source_kind=spec.get("source_kind") or "web",
                updated_at=card_data.get("updated_text") or context["display_local"],
                items=items,
                note="数据来自 TopHub / 今日热卖公开商品榜单。",
            )
        except Exception as exc:
            failure_reason = clean_text(str(exc)) or "抓取失败"

        if platform_payload is None:
            carried = stale_from_existing(spec, existing_root, context, failure_reason)
            platform_payload = carried or unavailable_platform(spec, context, failure_reason)
            meta_platforms[spec["key"]] = build_meta_entry(platform_payload, failure_reason)
        else:
            meta_platforms[spec["key"]] = build_meta_entry(platform_payload)
        products[spec["key"]] = platform_payload

    fresh_count = sum(1 for item in meta_platforms.values() if item["status"] == "fresh")
    stale_count = sum(1 for item in meta_platforms.values() if item["status"] == "stale")
    unavailable_count = sum(1 for item in meta_platforms.values() if item["status"] == "unavailable")

    notes = [
        "前端仅请求同域 /data/hot.json，不再直接请求外部 API。",
        "抖音优先使用 DailyHotApi；其余榜单优先使用 TopHub 公网公开页面。",
        "单个平台抓取失败时，会优先沿用仓库中上一次成功数据，并在 meta.platforms 中标记 stale / fallback。",
    ]
    if tophub_home_error:
        notes.append(f"本次 TopHub 首页抓取异常：{tophub_home_error}")

    return {
        "meta": {
            "version": 1,
            "timezone": "Asia/Shanghai",
            "generated_at": context["iso_utc"],
            "generated_at_local": context["display_local"],
            "generated_date": context["date_local"],
            "workflow_name": "Daily Hot Data Sync",
            "generator": "scripts/generate_hot_json.py",
            "summary": {
                "hot_platform_count": len(hot),
                "product_platform_count": len(products),
                "fresh_count": fresh_count,
                "stale_count": stale_count,
                "unavailable_count": unavailable_count,
            },
            "platforms": meta_platforms,
            "notes": notes,
        },
        "hot": hot,
        "products": products,
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    ensure_parent(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="抓取并生成 data/hot.json")
    parser.add_argument("--output", default=str(DATA_PATH), help="输出 JSON 路径")
    args = parser.parse_args()

    output_path = Path(args.output)
    existing_root = read_existing(output_path)
    payload = collect_data(existing_root)
    write_json(output_path, payload)


if __name__ == "__main__":
    main()
