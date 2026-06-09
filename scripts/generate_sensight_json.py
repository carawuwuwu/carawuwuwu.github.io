#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
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
WEIBO_ONLY_QUERY = "天猫618 京东618 小米618 国补 直播间 抽奖 福利 加码"

MIN_REPOSTS = 300
MIN_COMMENTS = 80
MIN_LIKES = 500
MIN_TOTAL_ENGAGEMENT = 1500

BRAND_WATCHLIST = [
    {"brand": "天猫", "platform": 3, "author_name": "天猫", "industry": "fashion"},
    {"brand": "京东", "platform": 3, "author_name": "京东", "industry": "food"},
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
    "tech": ["国补", "补贴", "手机", "家电", "平板", "空调", "耳机", "清洁电器", "汽车"],
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
INDUSTRY_LABEL = {
    "fashion": "服饰",
    "beauty": "美妆",
    "food": "食饮",
    "tech": "3C / 家电",
    "daily": "日化",
    "baby": "母婴",
    "edu": "教育",
}

INDUSTRY_TEMPLATE = {
    "fashion": {
        "summary": "服饰今天更适合用穿搭结果说服，再把直播权益和到手价压在后半句，先让人想象上身变化。",
        "hot_words": ["上身差异", "通勤防晒", "直播专属券", "夏季焕新", "显瘦腰线", "场景穿搭"],
        "content_angles": [
            "服饰内容先给出“穿上之后的变化”，再补券后价，转化会更顺。",
            "直播间重点说版型、面料、场景和尺码，而不是只念折扣。",
            "封面建议把“通勤 / 约会 / 防晒”这类场景词写在前面。",
        ],
        "pain_points": ["只讲便宜不讲上身效果", "用户担心版型不合适"],
        "recommended_action": "今天服饰优先走“场景种草 + 直播收口”的双段式承接。",
    },
    "beauty": {
        "summary": "美妆今天最需要把真实效果和肤质适配讲清，再叠加福利表达，避免只有成分没有结果。",
        "hot_words": ["高温持妆", "暴晒防护", "肤感实测", "券后组合", "修护搭配", "上脸对比"],
        "content_angles": [
            "美妆内容优先强调体感和结果图，而不是抽象成分名词堆叠。",
            "直播里把肤质、人群、使用顺序讲清，比单纯降价更能转。",
            "内容标题里建议把“暴晒 / 脱妆 / 熬夜”这种明确问题写出来。",
        ],
        "pain_points": ["用户怕踩雷", "看不到上脸结果难下单"],
        "recommended_action": "今天美妆优先用问题场景切入，再把赠品和券后价补上。",
    },
    "food": {
        "summary": "食饮今天更适合放大即时满足和囤货理由，不同子类必须分别写清“为什么现在就该买”。",
        "hot_words": ["夏日解渴", "低卡代餐", "囤货礼盒", "直播限时价", "办公室补给", "家庭分享"],
        "content_angles": [
            "食饮不要再统一写“囤货”，要按饮品、轻食、礼盒分开讲理由。",
            "内容里把入口场景写具体，会比泛泛讲性价比更有代入感。",
            "直播要突出“现在喝 / 现在吃 / 现在送”的即时动作。",
        ],
        "pain_points": ["用户怕囤多了不值", "看不到具体食用场景"],
        "recommended_action": "今天食饮优先按场景分货：解渴、代餐、送礼三条线分别做。",
    },
    "tech": {
        "summary": "3C / 家电今天仍然由补贴、换新和高客单决策解释驱动，内容必须把政策和体验一起讲透。",
        "hot_words": ["国补直降", "换新补贴", "版本建议", "体验实测", "家电焕新", "学生优惠"],
        "content_angles": [
            "3C 内容第一句话先说补贴范围和到手价，再补性能卖点。",
            "高客单一定要加“适合谁买”的版本建议，减少犹豫。",
            "直播里把政策步骤拆成 1-2-3，避免用户被门槛劝退。",
        ],
        "pain_points": ["政策没讲明白", "高客单信息过载"],
        "recommended_action": "今天 3C / 家电优先打补贴解释牌，再补实测和场景体验。",
    },
    "daily": {
        "summary": "日化今天要把家庭高频消耗和单次使用成本算清，重点不是便宜，而是“长期更省事”。",
        "hot_words": ["家庭补货", "单次成本", "除菌去味", "整箱更省", "夏季清洁", "囤货清单"],
        "content_angles": [
            "日化内容要写出“多久用完、一次用多少、全家能用多久”。",
            "前后效果差和使用频次，比单纯报券更能打动家庭决策。",
            "直播里把整箱 / 大包装和赠品组合成一套补货方案。",
        ],
        "pain_points": ["怕囤太多用不掉", "看不出和普通款差别"],
        "recommended_action": "今天日化优先做家庭补货方案，而不是孤立讲单件价格。",
    },
    "baby": {
        "summary": "母婴今天最重要的是安全感表达，不同二级类目要分别回答护理、喂养和出行的具体顾虑。",
        "hot_words": ["安心材质", "夏季红屁屁", "整夜安睡", "辅食喂养", "出行安全", "妈妈囤货"],
        "content_angles": [
            "母婴内容先回答家长最担心的问题，再谈价格和福利。",
            "护理和喂养不能混写，要按场景分别解决焦虑。",
            "直播里多做材质、吸收、安装和安全细节展示。",
        ],
        "pain_points": ["家长对安全极敏感", "只讲优惠无法建立信任"],
        "recommended_action": "今天母婴优先做“顾虑拆解型”表达，再加福利信息。",
    },
    "edu": {
        "summary": "教育今天要按暑期补课、学习工具、升学规划三类决策链分开写，不能再统一讲“提分”。",
        "hot_words": ["暑期节奏", "试听体验", "学习工具", "规划答疑", "家长决策", "AI辅助学习"],
        "content_angles": [
            "教育内容一定要区分“马上报名”和“先咨询再决策”两种链路。",
            "学习机与课程的卖点完全不同，必须拆开表达。",
            "规划咨询更适合用案例和顾问信任感，而不是促销话术。",
        ],
        "pain_points": ["家长怕踩坑", "看不清短期与长期收益"],
        "recommended_action": "今天教育优先按决策成熟度分层沟通，而不是一套文案打全场。",
    },
}

SUBCATEGORY_TEMPLATE = {
    "服饰 > 防晒衣": {
        "summary": "防晒衣今天要把“通勤不闷”和“户外不狼狈”讲成结果图，重点是体感差异而不是只说 UPF 数字。",
        "hot_words": ["地铁不闷汗", "办公室空调防冷", "骑车不粘身", "直播试穿对比", "折叠好带", "通勤防晒"],
        "content_angles": [
            "先拍通勤 10 分钟后的状态，再讲面料和券后价。",
            "直播里重点做腋下、后背、帽檐这三个细节展示。",
            "标题建议突出“出门不想撑伞的人”这类明确人群。",
        ],
        "pain_points": ["怕闷热不透气", "担心版型显壮"],
        "recommended_action": "把“暴晒通勤实测”做成短视频主钩子，再用直播做试穿收口。",
    },
    "服饰 > 连衣裙": {
        "summary": "连衣裙今天更该放大“约会 / 出游 / 拍照”三种结果感，把氛围感和显瘦点讲具体。",
        "hot_words": ["约会出片", "收腰比例", "旅行拍照", "轻法式氛围", "百元高级感", "不挑身材"],
        "content_angles": [
            "内容封面先给全身比例变化，再说面料和活动价。",
            "直播里把走路摆动感和坐下不尴尬这类细节讲出来。",
            "适合用“出游行李箱里只带这一条”的表达做种草。",
        ],
        "pain_points": ["怕显胯显肚子", "担心实物没氛围感"],
        "recommended_action": "用“拍照一条出片”的结果型内容承接出游人群。",
    },
    "服饰 > 男士凉感上装": {
        "summary": "男士凉感上装今天要强调“上班不皱、见客户不油腻”，核心不是潮，而是省心和体面。",
        "hot_words": ["轻商务不板正", "久坐不皱", "父亲节焕新", "办公室速干", "基础色百搭", "男装降温感"],
        "content_angles": [
            "优先拍地铁通勤和办公室久坐两个真实场景。",
            "直播中多做肩线、版型、汗湿后状态对比。",
            "文案可用“不会穿搭也能直接拿走”的懒人表达。",
        ],
        "pain_points": ["怕像工服", "怕面料一出汗就贴身"],
        "recommended_action": "用“上班不用想搭配”的省心感切入，更容易带动下单。",
    },
    "美妆 > 防晒": {
        "summary": "防晒今天必须回答“暴晒后会不会糊、会不会搓泥”，重点是高温通勤下的稳定表现。",
        "hot_words": ["暴晒不斑驳", "上脸不泛白", "高温不糊", "通勤补涂", "妆前不搓泥", "户外续航"],
        "content_angles": [
            "先拍室外大太阳下的妆面状态，再解释防护力。",
            "直播里把成膜速度和跟底妆打不打架讲清。",
            "标题建议直接写“油皮 / 混油 / 通勤党”人群标签。",
        ],
        "pain_points": ["怕厚重假白", "担心补涂毁妆"],
        "recommended_action": "把“通勤 8 小时防晒测试”作为当天核心内容资产。",
    },
    "美妆 > 底妆": {
        "summary": "底妆今天要放大“高温一天不暗沉”的结果，重点是妆效持续，不是单点遮瑕参数。",
        "hot_words": ["高温持妆", "毛孔不浮粉", "下午不发灰", "轻薄服帖", "口罩不斑驳", "黄黑皮友好"],
        "content_angles": [
            "内容最好做上午 / 下午妆面状态对照。",
            "直播里把不同肤质、不同瑕疵程度的上脸差异说清。",
            "适合用“晚高峰照镜子还能见人”这种真实表达。",
        ],
        "pain_points": ["怕假面感重", "怕下午氧化变黄"],
        "recommended_action": "用全天跟妆对比来放大底妆的稳定度，转化更直接。",
    },
    "美妆 > 修护精华": {
        "summary": "修护精华今天更该从“熬夜、晒后、换季泛红”三个问题切入，让用户先对号入座。",
        "hot_words": ["熬夜回魂", "晒后镇静", "泛红急救", "屏障维稳", "油敏同养", "夏天也能叠涂"],
        "content_angles": [
            "先拍皮肤状态崩掉的时刻，再讲怎么救回来。",
            "直播中重点回答“几天见效、能不能和其他产品叠用”。",
            "内容里最好用问题肌时间线，而不是抽象成分科普。",
        ],
        "pain_points": ["怕没感知", "怕闷痘或搓泥"],
        "recommended_action": "把“问题爆发时的救火方案”做成内容主线，比成分长文更有效。",
    },
    "食饮 > 饮品": {
        "summary": "饮品今天要围绕“高温解渴、办公室续命、运动后补水”讲即时爽感，不能再泛泛写囤货。",
        "hot_words": ["冰镇回魂", "运动后补水", "办公室续杯", "低负担解渴", "夏日清爽口感", "随手开喝"],
        "content_angles": [
            "优先拍第一口降温感和冰杯场景，立刻让人想喝。",
            "直播中主打成箱更省、冷藏更爽、搭餐更合适三类理由。",
            "标题建议直接写“下午犯困 / 户外暴晒 / 健身后”这些使用时刻。",
        ],
        "pain_points": ["怕买到太甜的", "担心囤多了喝不完"],
        "recommended_action": "用“夏天随手开一瓶就舒服”这类即时场景打穿饮品转化。",
    },
    "食饮 > 轻食": {
        "summary": "轻食今天必须突出“低卡但不空腹、忙也能吃得干净”，核心是身材管理和效率兼顾。",
        "hot_words": ["低卡饱腹", "办公室代餐", "健身后补给", "晚餐不负罪", "三分钟开吃", "体重管理友好"],
        "content_angles": [
            "内容里先说热量和饱腹感，再讲价格，顺序不能反。",
            "直播最好做真实开盒、份量、饱腹时长和口味评价。",
            "适合把“减脂期最怕饿到报复性进食”这类痛点写在前面。",
        ],
        "pain_points": ["怕吃不饱", "怕健康餐难吃"],
        "recommended_action": "把“减脂又要扛饿”的双重需求讲透，会比单纯低卡更能成交。",
    },
    "食饮 > 零食礼盒": {
        "summary": "零食礼盒今天更该强调“送礼有面子、家庭分享不踩雷、囤在家里马上能开”的场景复用感。",
        "hot_words": ["家庭分享装", "办公室分食", "送礼不出错", "追剧囤货", "开箱氛围感", "朋友来家里有得拿"],
        "content_angles": [
            "先拍开箱层次感和分量，再讲会场价。",
            "直播里多做多人试吃和“适合送谁”的推荐。",
            "标题建议写“送同事 / 送家人 / 囤家里”这种明确用途。",
        ],
        "pain_points": ["怕华而不实", "担心口味过于单一"],
        "recommended_action": "把“送得出手 + 自己也能吃”这个双用途逻辑讲清楚。",
    },
    "3C > 手机 / 平板": {
        "summary": "手机 / 平板今天必须围绕“补贴后到底便宜多少、哪个版本更值得买”来讲，先消除算账焦虑。",
        "hot_words": ["补贴后到手价", "学生认证加码", "版本别买错", "换机一步到位", "续航不用慌", "暑期开黑装备"],
        "content_angles": [
            "第一屏直接写补贴后价格和适合谁买。",
            "直播里把标准版 / 高配版差异讲得像选套餐一样清楚。",
            "内容适合用“预算 X 元怎么选”做决策型标题。",
        ],
        "pain_points": ["看不懂补贴叠法", "不知道哪一档最值"],
        "recommended_action": "用“预算决策表 + 补贴步骤”两件套来收口手机 / 平板人群。",
    },
    "3C > 清洁电器": {
        "summary": "清洁电器今天最有效的是“脏污强对比 + 家务节省时间”这两件事，别只说参数。",
        "hot_words": ["毛发一遍吸净", "自清洁省事", "拖地不弯腰", "宠物家庭刚需", "高温杀菌", "厨房重污实测"],
        "content_angles": [
            "内容开头先上极脏场景，三秒内让用户看到差距。",
            "直播重点讲自清洁流程、续航和噪音，不要堆配置名词。",
            "适合用“有娃 / 有宠 / 懒人家务”三类人群做分发。",
        ],
        "pain_points": ["怕买回去闲置", "担心清洗麻烦"],
        "recommended_action": "把“家务时间直接减半”的结果拍出来，比技术参数更能打。",
    },
    "3C > 影音外设": {
        "summary": "影音外设今天要放大“沉浸体验可视化”，把听感、延迟和场景氛围拍到能被感知。",
        "hot_words": ["延迟够低", "客厅沉浸感", "电竞听脚步", "办公室降噪", "连上就能用", "外放氛围感"],
        "content_angles": [
            "内容里把游戏、通勤、观影三种场景拆开演示。",
            "直播中做连接速度、延迟和降噪前后对比。",
            "适合用“这不是参数，这是体验差”这种翻译式表达。",
        ],
        "pain_points": ["怕参数看不懂", "担心到手体验不明显"],
        "recommended_action": "优先做体验可视化，而不是堆规格参数图表。",
    },
    "日化 > 洗护清洁": {
        "summary": "洗护清洁今天要把“去污力 / 留香 / 大包装更省”分开说，让家庭主力决策者快速算清。",
        "hot_words": ["顽渍一遍掉", "留香一整天", "全家大桶装", "洗护补货", "除味不刺鼻", "夏季汗味处理"],
        "content_angles": [
            "前后对比必须真拍脏污和异味场景，不要只拍包装。",
            "直播里多讲大桶能用多久、一次用多少、适合几口之家。",
            "标题适合用“夏天衣服难洗 / 家里总有味”这类问题切入。",
        ],
        "pain_points": ["怕效果和普通款没差别", "怕大包装不好收纳"],
        "recommended_action": "用“问题解决 + 用量账单”双重表达来打洗护清洁。",
    },
    "日化 > 驱蚊 / 除菌": {
        "summary": "驱蚊 / 除菌今天的关键不是便宜，而是“家里有老人孩子能不能放心用”的安全感。",
        "hot_words": ["整晚少打扰", "卧室可安心用", "夏季细菌焦虑", "户外回家除菌", "儿童房友好", "气味不过分"],
        "content_angles": [
            "内容里先回答刺激不刺激、能不能长时间开。",
            "直播更适合做卧室、客厅、出游三种场景方案搭配。",
            "适合把“夏天最烦的两件事：蚊子和异味”做成主标题。",
        ],
        "pain_points": ["怕气味冲", "担心对孩子不友好"],
        "recommended_action": "把“全家都能安心用”放在促销信息前面，更容易建立信任。",
    },
    "日化 > 纸品 / 个护": {
        "summary": "纸品 / 个护今天要强调“消耗快、家里总要备、补货一次顶很久”，重点是补货效率。",
        "hot_words": ["家里永远缺", "大规格补货", "抽取顺手", "通勤随身包", "柔软不掉屑", "浴室囤货位"],
        "content_angles": [
            "内容里把家里多个使用点位拍出来，强化高频消耗感。",
            "直播重点讲规格差异、张数、层数和单次成本。",
            "适合用“每次用到最后才想起该补货”这种真实生活表达。",
        ],
        "pain_points": ["怕买多了占地方", "担心质量和厚度不稳"],
        "recommended_action": "围绕“家庭补货一步到位”做组合装和箱规承接。",
    },
    "母婴 > 纸尿裤 / 湿巾": {
        "summary": "纸尿裤 / 湿巾今天要直击“整夜漏不漏、红不红屁股、出门带着方不方便”这三个核心顾虑。",
        "hot_words": ["整夜安睡", "外出一包搞定", "透气不闷屁", "湿巾一抽不断", "夏天屁屁护理", "新手爸妈不踩雷"],
        "content_angles": [
            "内容要优先拍吸收、回渗和便携收纳细节。",
            "直播里把尺码、体重、夜用 / 日用区别讲明白。",
            "标题适合用“夏天最怕红屁屁”这类焦虑点开场。",
        ],
        "pain_points": ["怕反渗起坨", "担心闷热不透气"],
        "recommended_action": "先讲安心睡整夜，再补整箱价和赠品，顺序不能反。",
    },
    "母婴 > 夏季护理": {
        "summary": "夏季护理今天必须围绕“出汗、晒红、痱子、蚊虫”四类高频问题分开解决，不能再泛化成日常护理。",
        "hot_words": ["晒后舒缓", "痱子护理", "出汗不黏腻", "洗澡后好吸收", "婴童防蚊", "夏天清爽不刺激"],
        "content_angles": [
            "内容先拍夏天最常见的不适状态，再给对应护理方案。",
            "直播中要说清使用顺序、频次和适龄阶段。",
            "适合用“宝宝夏天最容易闹的几个点”做系列内容。",
        ],
        "pain_points": ["怕成分刺激", "不知道该先解决哪个问题"],
        "recommended_action": "把护理问题按“晒、痒、热、叮”四类拆开表达，更容易被家长收藏。",
    },
    "母婴 > 喂养 / 安全座椅": {
        "summary": "喂养 / 安全座椅今天更适合打“操作是否省心”和“安全是否有证据”，减少大件决策的不确定感。",
        "hot_words": ["一键安装", "坐得住不哭闹", "辅食喂养顺手", "出门固定更安心", "材质看得见", "成长阶段适配"],
        "content_angles": [
            "内容里把安装步骤和实际坐姿直接演示出来。",
            "直播中重点回答角度、清洗、适配年龄和车内空间问题。",
            "适合用“第一次买也不会装错”这类低门槛表达。",
        ],
        "pain_points": ["怕安装麻烦", "担心买完不适配孩子阶段"],
        "recommended_action": "把“操作省心 + 安全可解释”作为喂养 / 出行大件的核心话术。",
    },
    "教育 > 暑期课程": {
        "summary": "暑期课程今天不能只讲提分，要讲“暑假两个月到底补什么、怎么安排节奏”这类决策问题。",
        "hot_words": ["暑假别掉队", "查漏补缺节奏", "先试听再报名", "假期作息安排", "衔接关键期", "家长省心排课"],
        "content_angles": [
            "内容里先给暑期时间规划表，再引出课程承接。",
            "直播更适合做“现在基础在哪、该补哪块”的顾问式沟通。",
            "标题建议写“暑假最怕浪费时间”这种家长焦虑。",
        ],
        "pain_points": ["怕报多了孩子扛不住", "担心补课方向错"],
        "recommended_action": "先卖“节奏规划”再卖课程，会比直接促销更有说服力。",
    },
    "教育 > 学习机 / AI 工具": {
        "summary": "学习机 / AI 工具今天最需要证明“孩子会不会真用、家长会不会真省心”，不要停留在功能罗列。",
        "hot_words": ["不会闲置", "拍题真快", "家长能盯进度", "暑假自驱学习", "AI讲题更懂", "错题自动整理"],
        "content_angles": [
            "内容里要拍真实使用流程，从开机到解决一道题。",
            "直播中重点回答年龄段、学科匹配和是否会变成吃灰机。",
            "适合用“陪学负担能不能减掉一半”这种结果表达。",
        ],
        "pain_points": ["怕功能花哨没用", "担心孩子三天热度"],
        "recommended_action": "把“孩子愿不愿意打开用”作为学习机内容的第一判断点。",
    },
    "教育 > 规划咨询 / 升学": {
        "summary": "规划咨询 / 升学今天更该卖“专业判断和路径清晰感”，核心不是优惠，而是减少家长信息焦虑。",
        "hot_words": ["升学路径图", "志愿早规划", "一对一答疑", "家长决策支持", "阶段目标拆解", "信息差补齐"],
        "content_angles": [
            "内容里多用真实案例和节点提醒，而不是模板化金句。",
            "直播里适合做问题答疑、路径拆解和个性化判断展示。",
            "标题最好写“现在不看，后面容易错过什么”这类提醒型表达。",
        ],
        "pain_points": ["家长怕走弯路", "不确定咨询值不值"],
        "recommended_action": "把“少走弯路”做成核心承诺，再用案例支撑专业度。",
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
    response = requests.post(url, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers=build_headers(action), timeout=timeout)
    response.raise_for_status()
    return response.json()


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
    result: List[str] = []
    seen = set()
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
    scores: Dict[str, int] = {}
    joined = "\n".join(texts)
    for industry, words in INDUSTRY_KEYWORDS.items():
        scores[industry] = sum(joined.count(word) for word in words)
    ordered = [k for k, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True) if scores[k] > 0]
    return ordered or ["tech", "beauty", "fashion"]


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
    lead = [item[0] for item in signal_counts.most_common(2)] or ["直播间券", "到手价"]
    pain = pain_counts.most_common(1)[0][0] if pain_counts else "规则理解"
    return {
        "trend_title": f"{lead[0]} + {lead[1]} 成为主驱动" if len(lead) > 1 else f"{lead[0]} 成为主驱动",
        "trend_desc": "社媒讨论更偏向直播权益、补贴说明和到手价表达。",
        "recommend_title": "先讲怎么领，再讲多便宜",
        "recommend_desc": f"今天最大的转化阻力仍是“{pain}”相关理解成本，建议把规则说明前置。",
        "industry_focus": " / ".join(INDUSTRY_LABEL.get(x, x) for x in top_industries[:3]),
        "industry_desc": "优先把最能接权益和补贴的行业先推起来，再补情绪和种草内容。",
    }


def build_today_signals(signal_counts: Counter, pain_counts: Counter, top_industries: List[str], brand_watch: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    lead = [item[0] for item in signal_counts.most_common(3)] or ["直播间券", "到手价", "国补"]
    pain = [item[0] for item in pain_counts.most_common(2)] or ["规则复杂", "买贵"]
    top_text = " / ".join(INDUSTRY_LABEL.get(x, x) for x in top_industries[:3])
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
            "title": "优先把高适配行业先推起来",
            "summary": f"从当前社媒和品牌动作看，{top_text} 更容易承接直播权益、补贴和价格型表达。",
            "evidence": "晨会可先把这些行业排在前面，再补纯情绪型话题。",
            "priority": "medium",
        },
        {
            "title": "品牌动作也在强化福利解释",
            "summary": brand_line,
            "evidence": "今天不是只报低价，而是把入口、场景和利益点串成一步一步可照做的话术。",
            "priority": "medium",
        },
    ]


def summarize_feature_reason(text: str, metrics: Dict[str, int]) -> str:
    if "抽" in text or "福利" in text or "红包" in text:
        return f"福利机制清晰、参与门槛低，真实互动已验证达到 {metrics['total_engagement']}。"
    if "国补" in text or "补贴" in text:
        return f"补贴信息直接影响高价决策，且互动总量达到 {metrics['total_engagement']}。"
    if "学生" in text or "暑假" in text:
        return f"节点人群明确、利益点集中，带来了 {metrics['comment_count']} 条以上评论互动。"
    return f"内容主题和节点强相关，且已验证为高互动帖子，总互动达到 {metrics['total_engagement']}。"


def summarize_feature_hook(text: str) -> str:
    if "抽" in text or "红包" in text:
        return "先抛出可参与的福利机制，再补活动节奏和入口。"
    if "补贴" in text or "国补" in text:
        return "第一句话先报政策 / 到手价，再补使用场景。"
    if "学生" in text or "暑假" in text:
        return "先点人群，再给专属权益，容易形成评论讨论。"
    return "封面先给利益点，正文再给时间节点和参与步骤。"


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
        elif "抽" in text or "红包" in text:
            insight = "最近动作明显在用福利机制放大讨论和转发。"
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


def build_industry_overrides() -> Dict[str, Any]:
    return {
        industry: {
            "summary": config["summary"],
            "hot_words": config["hot_words"][:6],
            "content_angles": config["content_angles"][:3],
            "pain_points": config["pain_points"][:2],
            "recommended_action": config["recommended_action"],
        }
        for industry, config in INDUSTRY_TEMPLATE.items()
    }


def build_subcategory_overrides() -> Dict[str, Any]:
    return {
        name: {
            "summary": config["summary"],
            "hot_words": config["hot_words"][:6],
            "content_angles": config["content_angles"][:3],
            "pain_points": config["pain_points"][:2],
            "recommended_action": config["recommended_action"],
        }
        for name, config in SUBCATEGORY_TEMPLATE.items()
    }


def parse_count_token(token: str) -> Optional[int]:
    token = safe_text(token)
    if not token:
        return None
    if token.endswith("万"):
        try:
            return int(float(token[:-1]) * 10000)
        except Exception:
            return None
    if token.isdigit():
        return int(token)
    return None


def extract_weibo_engagement_batch(urls: List[str], errors: List[str]) -> Dict[str, Dict[str, int]]:
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        errors.append(f"未安装 Playwright，无法做微博真实互动校验：{exc}")
        return {}

    metrics_by_url: Dict[str, Dict[str, int]] = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 2600})
        for url in urls:
            try:
                page.goto(url, wait_until="networkidle", timeout=120000)
                body = page.locator("body").inner_text(timeout=15000)
                lines = [safe_text(x) for x in body.splitlines() if safe_text(x)]
                if "分享这条博文" in lines:
                    share_idx = lines.index("分享这条博文")
                    prefix = lines[:share_idx]
                else:
                    prefix = lines[:60]
                numeric_tokens = [parse_count_token(x) for x in prefix]
                numeric_tokens = [x for x in numeric_tokens if x is not None]
                if len(numeric_tokens) < 3:
                    errors.append(f"微博互动校验失败：{url} 未提取到足够的互动数字")
                    continue
                repost_count, comment_count, like_count = numeric_tokens[-3:]
                metrics_by_url[url] = {
                    "repost_count": repost_count,
                    "comment_count": comment_count,
                    "like_count": like_count,
                    "total_engagement": repost_count + comment_count + like_count,
                }
            except Exception as exc:
                errors.append(f"微博互动校验失败：{url} -> {exc}")
        browser.close()
    return metrics_by_url


def collect_featured_candidates(author_results: List[Dict[str, Any]], extra_weibo_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    seen = set()
    for author in author_results:
        brand = author.get("selected_author_name") or author.get("author_name") or "品牌"
        for item in author.get("items") or []:
            url = item.get("url") or ""
            if "weibo.com" not in url or url in seen:
                continue
            seen.add(url)
            text = safe_text(item.get("content"))
            candidates.append(
                {
                    "brand": brand,
                    "platform": "微博",
                    "title": safe_text(item.get("title")) or short_text(text, 30),
                    "publish_time": item.get("publish_time") or "",
                    "url": url,
                    "summary": short_text(text, 150),
                    "raw_text": text,
                    "user_name": brand,
                }
            )
    return candidates


def build_featured_posts(candidates: List[Dict[str, Any]], errors: List[str]) -> List[Dict[str, Any]]:
    urls = [item["url"] for item in candidates]
    metrics_by_url = extract_weibo_engagement_batch(urls, errors)
    verified = []
    for item in candidates:
        metrics = metrics_by_url.get(item["url"])
        if not metrics:
            continue
        if metrics["repost_count"] < MIN_REPOSTS:
            continue
        if metrics["comment_count"] < MIN_COMMENTS:
            continue
        if metrics["like_count"] < MIN_LIKES:
            continue
        if metrics["total_engagement"] < MIN_TOTAL_ENGAGEMENT:
            continue
        verified.append(
            {
                **item,
                **metrics,
                "why_hot": summarize_feature_reason(item["raw_text"], metrics),
                "hook": summarize_feature_hook(item["raw_text"]),
                "tag": "已验证高互动",
            }
        )
    verified.sort(key=lambda x: x["total_engagement"], reverse=True)
    return verified[:3]


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
    verified_weibo_items: List[Dict[str, Any]] = []

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

    try:
        verified_weibo_items = (post_json(f"{BASE_SENSIGHT}/sensight/skill_social_search", {"query": WEIBO_ONLY_QUERY, "platforms": [3], "size": 12}, "social_search").get("items") or [])[:12]
    except Exception as exc:
        errors.append(f"social_search 微博高热候选失败：{exc}")

    for watch in BRAND_WATCHLIST:
        try:
            payload = {
                "platform": watch["platform"],
                "author_name": watch["author_name"],
                "size": 5,
                "page_number": 1,
            }
            result = post_json(f"{BASE_SENSIGHT}/sensight/skill_search_author_posts", payload, "search_author_posts")
            result["author_name"] = watch["author_name"]
            brand_raw.append(result)
        except Exception as exc:
            errors.append(f"品牌观察 {watch['author_name']} 失败：{exc}")

    merged_social = merge_social_results(social_items, pain_items)
    texts = [safe_text(item.get("title")) + " " + safe_text(item.get("summary")) for item in event_items]
    texts += [safe_text(item.get("title")) + " " + safe_text(item.get("content")) for item in merged_social]
    texts += [safe_text((item.get("items") or [{}])[0].get("content")) for item in brand_raw if item.get("items")]

    if not any(texts) and existing and args.allow_stale_fallback:
        print("No fresh Sensight data, keep existing data/sensight.json")
        return

    signal_counts = count_keywords(texts, SIGNAL_KEYWORDS)
    pain_counts = count_keywords(texts, PAIN_KEYWORDS)
    top_industries = industry_rank(texts)
    social_cards = build_social_items(merged_social)
    brand_watch = build_brand_watch(brand_raw)
    header = build_header(signal_counts, pain_counts, top_industries)
    today_signals = build_today_signals(signal_counts, pain_counts, top_industries, brand_watch)
    industry_overrides = build_industry_overrides()
    subcategory_overrides = build_subcategory_overrides()

    featured_candidates = collect_featured_candidates(brand_raw, verified_weibo_items)
    featured_posts = build_featured_posts(featured_candidates, errors)
    if not featured_posts:
        notes.append("当前未筛到满足真实互动量阈值的微博高热帖子，爆文拆解将显示空状态。")
    else:
        notes.append(f"已通过真实互动量校验筛出 {len(featured_posts)} 条微博高热帖子。")

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
            "version": 2,
            "timezone": "Asia/Shanghai",
            "generated_at": now.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "generated_at_local": now.strftime("%Y-%m-%d %H:%M:%S CST"),
            "generated_date": now.strftime("%Y-%m-%d"),
            "generator": "scripts/generate_sensight_json.py",
            "status": "partial" if errors else "success",
            "notes": notes,
            "errors": errors,
            "featured_post_rule": {
                "source": "微博公开正文页真实互动校验",
                "threshold": {
                    "repost_count": MIN_REPOSTS,
                    "comment_count": MIN_COMMENTS,
                    "like_count": MIN_LIKES,
                    "total_engagement": MIN_TOTAL_ENGAGEMENT,
                },
            },
        },
        "header": header,
        "today_signals": today_signals,
        "social_observations": {
            "summary": "这里展示的是社媒讨论样本，用来感受用户正在怎么说；不等同于高互动爆文。",
            "positive_keywords": positive_keywords,
            "pain_points": pain_keywords,
            "content_hooks": content_hooks,
            "items": social_cards,
        },
        "featured_posts": [
            {
                "platform": item["platform"],
                "title": item["title"],
                "user_name": item["user_name"],
                "brand": item["brand"],
                "publish_time": item["publish_time"],
                "url": item["url"],
                "summary": item["summary"],
                "why_hot": item["why_hot"],
                "hook": item["hook"],
                "tag": item["tag"],
                "metrics": {
                    "repost_count": item["repost_count"],
                    "comment_count": item["comment_count"],
                    "like_count": item["like_count"],
                    "total_engagement": item["total_engagement"],
                },
            }
            for item in featured_posts
        ],
        "brand_watch": brand_watch,
        "industry_overrides": industry_overrides,
        "subcategory_overrides": subcategory_overrides,
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
