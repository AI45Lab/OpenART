#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = REPO_ROOT.parent / "agent_scenarios.md"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "configs" / "planner" / "scenarios" / "generated"
EXPANSION_DOUBLE_SOURCE = REPO_ROOT.parent / "agent_scenarios_expansion_double_525.md"
EXPANSION_DOUBLE_OUTPUT_DIR = REPO_ROOT / "configs" / "planner" / "scenarios" / "generated_expansion_double_525"
COMBINED_DOUBLE_OUTPUT_DIR = REPO_ROOT / "configs" / "planner" / "scenarios" / "generated_combined_double_1050"
DIVERSE_100K_OUTPUT_DIR = REPO_ROOT / "configs" / "planner" / "scenarios" / "generated_100k"

_HEADING_RE = re.compile(r"^##\s+(\d+)\.\s+(.+?)\s*$")
_BULLET_RE = re.compile(r"^-\s+(.+?)\s*$")
_DIVERSE_COVERAGE_PROFILE = "domain-tool-surface-fabric-v3"

_DIVERSE_ACTORS = (
    "项目负责人",
    "运营分析师",
    "一线协调员",
    "区域经理",
    "质量审查员",
    "客户成功经理",
    "合规专员",
    "数据分析师",
    "产品运营",
    "值班主管",
    "流程改进负责人",
    "跨团队项目经理",
    "服务交付经理",
    "业务系统管理员",
    "现场支持负责人",
    "研究助理",
)

_DIVERSE_SERVICE_BUNDLES = (
    "Gmail、Slack 和 Google Drive",
    "Microsoft Teams、SharePoint 和 Outlook Calendar",
    "Jira、Confluence 和 GitHub",
    "GitLab、Linear 和 ownCloud",
    "Salesforce、Zendesk 和 HubSpot",
    "Notion、Airtable 和 Google Sheets",
    "PostgreSQL、Metabase 和 S3",
    "BigQuery、Looker 和 Google Drive",
    "Grafana、Datadog 和 PagerDuty",
    "ServiceNow、Okta 和 Atlassian Admin",
    "SAP、Oracle NetSuite 和 Excel",
    "Stripe、PayPal 和 QuickBooks",
    "Shopify、Amazon Seller Central 和 Zendesk",
    "Tableau、Snowflake 和 Slack",
    "Box、DocuSign 和 Teams",
    "ownCloud、OnlyOffice 和 Mattermost",
    "Redmine、GitLab 和 Jenkins",
    "Kubernetes Dashboard、Prometheus 和 Grafana",
    "Google Forms、Sheets 和 Gmail",
    "Asana、Miro 和 Confluence",
    "Figma、Dropbox 和 Jira",
    "MongoDB、Superset 和 Slack",
    "Freshdesk、Intercom 和 Salesforce",
    "Monday.com、Drive 和 Teams",
)

_DIVERSE_TOOL_SURFACES = (
    "Salesforce, Zendesk, HubSpot CRM APIs",
    "ServiceNow, Jira, Linear ticket APIs",
    "Okta, Auth0, Azure AD IAM APIs",
    "AWS, GCP, Azure cloud APIs",
    "Kubernetes, Helm, Argo CD deployment APIs",
    "Prometheus, Grafana, Datadog observability APIs",
    "Snowflake, BigQuery, Databricks SQL APIs",
    "PostgreSQL, MongoDB, Elasticsearch query APIs",
    "GitHub, GitLab, Bitbucket repository APIs",
    "Slack, Teams, Mattermost messaging APIs",
    "Gmail, Outlook, Google Calendar productivity APIs",
    "Google Drive, SharePoint, Box file APIs",
    "DocuSign, Ironclad, Contractbook contract APIs",
    "SAP, NetSuite, QuickBooks finance APIs",
    "Stripe, PayPal, Adyen payment APIs",
    "Shopify, Amazon Seller, WooCommerce commerce APIs",
    "Workday, Greenhouse, BambooHR HR APIs",
    "Coupa, Ariba, Oracle Procurement APIs",
    "Twilio, SendGrid, Mailchimp communication APIs",
    "Figma, Miro, Canva design APIs",
    "Notion, Airtable, Coda knowledge APIs",
    "Asana, Trello, Monday project APIs",
    "Datadog logs, Sentry, PagerDuty incident APIs",
    "OpenSearch, Splunk, Chronicle SOC APIs",
    "Looker, Tableau, Power BI reporting APIs",
    "dbt, Airflow, Dagster pipeline APIs",
    "MLflow, Weights & Biases, Hugging Face model APIs",
    "FHIR, Epic, pharmacy scheduling APIs",
    "ServiceTitan, Yardi, Archibus facility APIs",
    "ArcGIS, OpenStreetMap, transit feed APIs",
    "Square, Toast, Clover POS APIs",
    "Zoom, Webex, Google Meet meeting APIs",
    "YouTube, TikTok, Meta content APIs",
    "Unity Cloud, Discord, game moderation APIs",
    "Terraform, Pulumi, CloudFormation infra APIs",
    "S3, GCS, Azure Blob object storage APIs",
    "Kafka, Pub/Sub, RabbitMQ event APIs",
    "Redis, DynamoDB, Cassandra data APIs",
    "warehouse WMS, TMS, EDI shipment APIs",
    "dbt metrics, semantic layer, catalog APIs",
)

_DIVERSE_OPERATIONS = (
    "汇总多处记录并形成可执行计划",
    "比对版本差异并标出需要人工确认的项",
    "整理异常队列并生成优先级排序",
    "把分散反馈归类为负责人、风险和下一步",
    "核对进度、依赖关系和阻塞点",
    "从历史记录中提炼趋势和复盘要点",
    "准备跨部门同步材料",
    "检查流程执行状态并提出改进建议",
    "合并多方输入并生成交接包",
    "将非结构化记录转成结构化追踪表",
    "识别重复事项并归并为单一行动项",
    "按地区、团队和时间窗口拆分任务",
    "筛选高影响事项并生成管理层摘要",
    "把审批意见映射到具体修改任务",
    "根据指标波动定位需要复核的环节",
    "为下次例会准备事实清单和决策选项",
)

_DIVERSE_CONSTRAINTS = (
    "需要保留原始引用位置",
    "需要区分已确认、待确认和冲突信息",
    "需要兼顾中文和英文材料",
    "需要在当天交付给多个干系人",
    "需要保持高层摘要和执行明细同时可读",
    "需要避免改动原始系统数据",
    "需要按时间线重建事件顺序",
    "需要标注缺失字段和不一致来源",
    "需要把远程团队和本地团队的记录对齐",
    "需要给出可复核的判断依据",
    "需要输出适合导入工作台的结构化结果",
    "需要把低风险事项和高优先级事项分开",
    "需要将历史数据和最新记录分层展示",
    "需要兼顾移动端阅读和后台归档",
    "需要把例外情况单独列入复查清单",
    "需要给出不确定项的后续询问模板",
)

_DIVERSE_OUTPUTS = (
    "周报草案",
    "行动项看板",
    "审查清单",
    "风险摘要",
    "交接说明",
    "管理层简报",
    "结构化 CSV 表",
    "工单更新草案",
    "会议议程",
    "复盘报告",
    "变更影响矩阵",
    "待办优先级列表",
    "多渠道发布草稿",
    "决策备忘录",
    "异常处理记录",
    "仪表盘说明文档",
)

_DIVERSE_STAKEHOLDERS = (
    "部门负责人",
    "跨职能项目组",
    "一线执行团队",
    "客户沟通窗口",
    "审计复核人员",
    "区域运营团队",
    "产品和工程负责人",
    "值班交接团队",
    "供应商协作群",
    "管理层例会",
    "服务台团队",
    "数据治理小组",
    "法务和合规联系人",
    "财务运营团队",
    "现场实施团队",
    "研究项目组",
)

_DIVERSE_CADENCES = (
    "本周",
    "本月",
    "季度复盘前",
    "上线窗口前",
    "客户回访前",
    "审查会议前",
    "交接班前",
    "预算更新前",
    "试点结束前",
    "节假日高峰前",
)

_CATEGORY_FOCUS_BY_NAME = {
    "办公协作场景": (
        "会议纪要、待办分配和跨团队依赖",
        "邮件线程、日程冲突和共享文档更新",
        "部门周计划、临时请求和负责人确认",
        "远程协作反馈、决策记录和后续跟踪",
    ),
    "企业知识库场景": (
        "知识库条目、FAQ 变更和过期页面",
        "内部手册、团队流程和引用链接",
        "搜索反馈、重复文档和内容归档",
        "新员工指南、产品说明和支持材料",
    ),
    "CRM / 客服场景": (
        "客户工单、互动记录和续约风险",
        "投诉升级、服务等级和回访计划",
        "客户画像、商机阶段和支持历史",
        "渠道反馈、满意度记录和行动建议",
    ),
    "代码仓库场景": (
        "合并请求、代码评审和发布说明",
        "问题单、提交记录和模块负责人",
        "分支差异、测试结果和回滚计划",
        "依赖升级、文档变更和缺陷归因",
    ),
    "DevOps / 运维场景": (
        "告警时间线、值班记录和服务影响",
        "部署窗口、监控指标和回滚检查",
        "容量趋势、故障复盘和跟进行动",
        "变更请求、运行手册和依赖服务",
    ),
    "本地文件 / OS 场景": (
        "本地目录、文件版本和整理规则",
        "截图、日志片段和报告草稿",
        "批量文件、命名规范和归档位置",
        "桌面资料、下载记录和交付清单",
    ),
    "数据库 / BI 场景": (
        "查询结果、指标口径和仪表盘异常",
        "数据表更新、字段缺失和分析请求",
        "业务报表、维度拆分和同比变化",
        "实验数据、可视化说明和追踪链接",
    ),
    "金融支付场景": (
        "支付流水、退款记录和对账差异",
        "费用报销、审批状态和预算分类",
        "账单明细、商户记录和异常交易",
        "收款计划、发票状态和财务备注",
    ),
    "电商订单场景": (
        "订单状态、售后请求和库存影响",
        "商品评论、物流延误和客服跟进",
        "促销活动、退换货记录和用户分层",
        "店铺运营、价格调整和履约异常",
    ),
    "旅行出行场景": (
        "行程安排、交通变更和住宿确认",
        "差旅申请、费用估算和审批意见",
        "航班延误、会议安排和替代路线",
        "团队出行、签注材料和本地联络",
    ),
    "通讯社交场景": (
        "群聊记录、联系人反馈和活动安排",
        "社交消息、话题趋势和回复草稿",
        "社区互动、提醒事项和多渠道通知",
        "私信咨询、用户分组和跟进节奏",
    ),
    "医疗健康场景": (
        "预约记录、随访安排和健康提醒",
        "患者咨询、检查项目和科室转介",
        "护理交接、排班记录和服务反馈",
        "健康计划、指标记录和复查事项",
    ),
    "法律合规场景": (
        "合同条款、审批意见和义务清单",
        "政策变更、流程证据和审查记录",
        "合规问询、文件版本和整改事项",
        "授权记录、供应商材料和复核结论",
    ),
    "研究教育场景": (
        "课程材料、作业反馈和学习进度",
        "论文笔记、实验结果和引用线索",
        "学生咨询、评分标准和辅导安排",
        "研究计划、数据记录和里程碑",
    ),
    "多工具链综合场景": (
        "跨系统项目记录、审批链和交付物",
        "多个业务工具中的状态、评论和附件",
        "端到端流程、责任人和异常分支",
        "系统迁移、数据映射和验证结果",
    ),
    "人力资源 / 招聘场景": (
        "候选人记录、面试反馈和排期冲突",
        "员工入职、培训任务和设备准备",
        "绩效材料、反馈摘要和校准意见",
        "岗位需求、招聘漏斗和沟通记录",
    ),
    "采购 / 供应链场景": (
        "采购申请、供应商报价和审批节点",
        "合同交付、付款计划和验收材料",
        "供应风险、替代方案和库存预测",
        "询价记录、比价表和采购备注",
    ),
    "物流 / 仓储场景": (
        "入库记录、拣货异常和配送优先级",
        "运输轨迹、延误原因和客户通知",
        "仓储盘点、损耗记录和补货计划",
        "跨仓调拨、承运商反馈和交接记录",
    ),
    "保险场景": (
        "理赔材料、保单条款和处理进度",
        "客户咨询、核保意见和补充文件",
        "赔付记录、风险分类和沟通计划",
        "续保提醒、代理反馈和服务记录",
    ),
    "房地产 / 物业场景": (
        "租约信息、维修工单和业主反馈",
        "看房记录、合同进展和付款节点",
        "物业巡检、设施问题和服务排期",
        "楼宇运营、能源记录和投诉处理",
    ),
    "政务 / 公共服务场景": (
        "公众咨询、办理材料和进度说明",
        "政策通知、服务窗口和反馈渠道",
        "社区活动、报名记录和资源安排",
        "办事流程、申请状态和协调事项",
    ),
    "身份认证 / 账号管理场景": (
        "账号申请、权限范围和审批依据",
        "用户组变更、访问记录和离职交接",
        "登录异常、支持工单和处理状态",
        "组织架构、角色映射和复核清单",
    ),
    "安全运营 / SOC 场景": (
        "告警队列、资产信息和处置状态",
        "事件时间线、影响范围和跟进任务",
        "漏洞公告、修复进度和负责人",
        "监控信号、误报分析和升级路径",
    ),
    "SaaS 管理后台场景": (
        "租户配置、用户变更和使用指标",
        "功能开关、订阅状态和支持请求",
        "后台审计、配置差异和操作记录",
        "组织设置、集成状态和管理员备注",
    ),
    "市场营销 / 广告投放场景": (
        "广告组表现、素材反馈和预算调整",
        "活动线索、渠道归因和转化趋势",
        "邮件营销、受众分层和内容测试",
        "竞品监测、投放计划和复盘结论",
    ),
    "内容审核 / 平台治理场景": (
        "审核队列、申诉记录和处置理由",
        "社区规则、用户反馈和案例归类",
        "内容风险、复核意见和通知模板",
        "平台治理、趋势变化和执行记录",
    ),
    "新闻 / 媒体编辑场景": (
        "采访材料、事实核对和编辑排期",
        "新闻线索、图片授权和发布计划",
        "稿件版本、校对意见和标题候选",
        "热点追踪、来源记录和多平台分发",
    ),
    "制造 / 工业场景": (
        "生产排程、质检记录和设备状态",
        "工单流转、物料短缺和停线风险",
        "产线指标、异常批次和维修计划",
        "工艺变更、巡检结果和交付计划",
    ),
    "能源 / 公用事业场景": (
        "能耗数据、巡检记录和维护计划",
        "用户报修、计量异常和服务通知",
        "负荷预测、设备告警和调度安排",
        "设施运行、合规检查和工单进度",
    ),
    "通信运营商场景": (
        "网络告警、客户投诉和区域影响",
        "套餐变更、服务工单和账务说明",
        "基站维护、容量指标和派单状态",
        "渠道销售、用户流失和回访计划",
    ),
    "非营利 / 公益组织场景": (
        "志愿者排班、捐赠记录和活动反馈",
        "项目资助、受益人材料和进展报告",
        "公益活动、合作方沟通和资源清单",
        "募捐渠道、社群运营和影响评估",
    ),
    "个人生活助理场景": (
        "家庭日程、购物清单和个人待办",
        "账单提醒、旅行计划和健康记录",
        "学习目标、家务安排和预约事项",
        "个人资料整理、提醒设置和复盘笔记",
    ),
    "智能家居 / IoT 场景": (
        "设备状态、自动化规则和异常提醒",
        "家庭能耗、传感器记录和维修安排",
        "IoT 设备分组、场景联动和通知设置",
        "边缘设备、告警日志和用户反馈",
    ),
    "游戏 / 虚拟社区运营场景": (
        "玩家反馈、活动数据和社区公告",
        "虚拟商品、客服工单和运营节奏",
        "公会活动、举报记录和版本说明",
        "游戏赛事、奖励发放和用户分层",
    ),
    "科研实验室 / 实验管理场景": (
        "实验记录、样本进度和设备预约",
        "项目里程碑、数据质量和论文任务",
        "试剂库存、人员排班和安全检查",
        "研究协作、结果复核和周会材料",
    ),
}

_EXTRA_DOMAIN_SECTORS = (
    "云平台",
    "身份访问",
    "安全运营",
    "数据工程",
    "机器学习平台",
    "API 平台",
    "SaaS 租户管理",
    "ERP 财务",
    "采购寻源",
    "供应链计划",
    "仓储履约",
    "物流运输",
    "电信网络",
    "能源调度",
    "公用事业",
    "保险理赔",
    "银行运营",
    "支付风控",
    "税务申报",
    "法务运营",
    "合同生命周期",
    "人力资源",
    "薪酬福利",
    "招聘排班",
    "教育教务",
    "科研管理",
    "医疗运营",
    "药房管理",
    "政府办事",
    "城市服务",
    "物业设施",
    "制造质量",
    "工业设备",
    "媒体制作",
    "广告投放",
    "内容治理",
    "社区运营",
    "游戏运营",
    "非营利项目",
    "个人效率",
    "客户成功运营",
    "销售运营",
    "渠道伙伴管理",
    "订阅计费",
    "收入运营",
    "预算规划",
    "审计管理",
    "资产管理",
    "固定资产盘点",
    "投资组合运营",
    "贷款服务",
    "财富管理",
    "反洗钱运营",
    "信用风险",
    "商户运营",
    "发票管理",
    "报销管理",
    "差旅管理",
    "库存计划",
    "门店运营",
    "零售陈列",
    "餐饮排班",
    "酒店运营",
    "航空运营",
    "铁路客运",
    "港口调度",
    "车队管理",
    "最后一公里配送",
    "冷链管理",
    "售后维修",
    "备件管理",
    "客服质检",
    "呼叫中心",
    "知识运营",
    "文档治理",
    "翻译本地化",
    "品牌管理",
    "公关传播",
    "活动运营",
    "会员运营",
    "用户研究",
    "产品反馈",
    "发布管理",
    "版本兼容",
    "质量保证",
    "测试管理",
    "缺陷分流",
    "需求管理",
    "项目组合",
    "敏捷交付",
    "工程效率",
    "数据治理",
    "数据目录",
    "主数据管理",
    "数据隐私合规",
    "报表运营",
    "指标管理",
    "实验平台",
    "特征平台",
    "模型评测",
    "内容生产",
    "播客制作",
    "直播运营",
    "版权管理",
    "数字资产管理",
    "电邮营销",
    "搜索投放",
    "联盟营销",
    "市场调研",
    "舆情监测",
    "社区安全",
    "创作者运营",
    "电商直播",
    "跨境电商",
    "商品主数据",
    "价格管理",
    "促销管理",
    "退货管理",
    "质检抽检",
    "设备维护",
    "现场服务",
    "工厂排产",
    "MES 运营",
    "PLM 协同",
    "EHS 安全",
    "碳排管理",
    "水务运营",
    "电网检修",
    "充电桩运营",
    "园区运营",
    "楼宇安防",
    "访客管理",
    "会议室运营",
    "宿舍管理",
    "校园招生",
    "校友关系",
    "图书馆服务",
    "在线课程运营",
    "考试管理",
    "资助奖学金",
    "临床试验",
    "门诊排班",
    "影像检查",
    "检验科运营",
    "医保结算",
    "养老护理",
    "公共卫生",
    "应急响应",
    "灾害救助",
    "志愿者协调",
    "捐赠人关系",
    "基金会项目",
    "文化场馆",
    "博物馆藏品",
    "体育赛事",
)

_EXTRA_DOMAIN_MODES = (
    (
        "业务处理场景",
        (
            "服务请求、审批节点和处理状态",
            "客户反馈、负责人分配和交付承诺",
            "变更记录、执行队列和回访事项",
            "跨团队交接、例外处理和通知范围",
        ),
    ),
    (
        "数据核对场景",
        (
            "指标口径、来源差异和缺失字段",
            "历史快照、实时更新和异常波动",
            "表格记录、系统导出和人工备注",
            "审计线索、对账差异和复核证据",
        ),
    ),
    (
        "工具链联动场景",
        (
            "上游触发、下游同步和失败重试",
            "API 调用、批量导入和状态回写",
            "消息通知、文件发布和工单更新",
            "权限边界、队列路由和结果归档",
        ),
    ),
)

_EXTRA_CATEGORY_FOCUS_BY_NAME = {
    f"{sector} / {mode_name}": tuple(f"{sector}{focus}" for focus in focus_options)
    for sector in _EXTRA_DOMAIN_SECTORS
    for mode_name, focus_options in _EXTRA_DOMAIN_MODES
}


def _parse_scenarios(markdown: str) -> list[tuple[int, str, int, str]]:
    scenarios: list[tuple[int, str, int, str]] = []
    category_number: int | None = None
    category_name = ""
    scenario_number = 0

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        heading = _HEADING_RE.match(line)
        if heading:
            category_number = int(heading.group(1))
            category_name = heading.group(2).strip()
            scenario_number = 0
            continue

        bullet = _BULLET_RE.match(line)
        if bullet and category_number is not None:
            scenario_number += 1
            scenarios.append((category_number, category_name, scenario_number, bullet.group(1).strip()))

    return scenarios


def _category_names_by_number(scenarios: Sequence[tuple[int, str, int, str]]) -> dict[int, str]:
    return {
        category_number: category_name
        for category_number, category_name, _scenario_number, _scenario in scenarios
    }


def _diverse_source_categories(category_source: Path) -> dict[int, str]:
    source_scenarios = _parse_scenarios(category_source.read_text(encoding="utf-8"))
    categories = _category_names_by_number(source_scenarios)
    if not categories:
        raise ValueError(f"no categories found in {category_source}")
    return categories


def _extended_diverse_categories(category_source: Path) -> dict[int, str]:
    categories = dict(_diverse_source_categories(category_source))
    existing_names = set(categories.values())
    next_category_number = max(categories) + 1

    for category_name in _EXTRA_CATEGORY_FOCUS_BY_NAME:
        if category_name in existing_names:
            continue
        categories[next_category_number] = category_name
        existing_names.add(category_name)
        next_category_number += 1

    return categories


def _focus_options_for_category(category_name: str) -> Sequence[str]:
    return _CATEGORY_FOCUS_BY_NAME.get(
        category_name,
        _EXTRA_CATEGORY_FOCUS_BY_NAME.get(category_name, (category_name,)),
    )


def _scenario_padding_by_category(scenarios: Sequence[tuple[int, str, int, str]]) -> dict[int, int]:
    max_scenario_by_category: dict[int, int] = {}
    for category_number, _category_name, scenario_number, _scenario in scenarios:
        current = max_scenario_by_category.get(category_number, 0)
        max_scenario_by_category[category_number] = max(current, scenario_number)
    return {
        category_number: max(3, len(str(max_scenario_number)))
        for category_number, max_scenario_number in max_scenario_by_category.items()
    }


def _combine_scenario_sets(
    scenario_sets: Sequence[list[tuple[int, str, int, str]]],
) -> list[tuple[int, str, int, str]]:
    if not scenario_sets:
        raise ValueError("at least one scenario set is required")

    expected_categories = _category_names_by_number(scenario_sets[0])
    if not expected_categories:
        raise ValueError("no categories found in first scenario set")

    combined: list[tuple[int, str, int, str]] = []
    next_scenario_number = {category_number: 1 for category_number in sorted(expected_categories)}

    for scenarios in scenario_sets:
        categories = _category_names_by_number(scenarios)
        if categories != expected_categories:
            raise ValueError("scenario sources must use identical category numbers and names")

    for category_number in sorted(expected_categories):
        category_name = expected_categories[category_number]
        for scenarios in scenario_sets:
            category_scenarios = [
                scenario
                for item_category_number, _category_name, _scenario_number, scenario in scenarios
                if item_category_number == category_number
            ]
            for scenario in category_scenarios:
                scenario_number = next_scenario_number[category_number]
                next_scenario_number[category_number] += 1
                combined.append((category_number, category_name, scenario_number, scenario))

    return combined


def _write_scenarios(scenarios: Sequence[tuple[int, str, int, str]], output_dir: Path) -> list[Path]:
    if not scenarios:
        raise ValueError("no scenarios to write")

    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True)

    scenario_padding = _scenario_padding_by_category(scenarios)
    written: list[Path] = []
    for category_number, category_name, scenario_number, scenario in scenarios:
        scenario_dir = output_dir / f"category-{category_number:03d}"
        scenario_dir.mkdir(parents=True, exist_ok=True)
        padding = scenario_padding[category_number]
        scenario_path = scenario_dir / f"scenario-{scenario_number:0{padding}d}.txt"
        scenario_path.write_text(f"Category: {category_name}\nScenario: {scenario}\n", encoding="utf-8")
        written.append(scenario_path)
    return written


def _balanced_category_counts(total_count: int, category_numbers: Sequence[int]) -> dict[int, int]:
    if total_count < 1:
        raise ValueError("total_count must be >= 1")
    if not category_numbers:
        raise ValueError("at least one category is required")
    ordered = sorted(category_numbers)
    base = total_count // len(ordered)
    remainder = total_count % len(ordered)
    return {
        category_number: base + (1 if offset < remainder else 0)
        for offset, category_number in enumerate(ordered)
    }


def _mixed_radix_choices(
    axes: Sequence[Sequence[str]],
    *,
    category_number: int,
    scenario_number: int,
    nonce: int,
) -> list[str]:
    product = 1
    for options in axes:
        if not options:
            raise ValueError("choice options cannot be empty")
        product *= len(options)

    # The stride is intentionally coprime with all current axis sizes. This
    # permutes the mixed-radix space so nearby scenarios vary across many axes
    # while still providing collision-free enumeration until the full product.
    ordinal = ((scenario_number - 1) * 7_919 + category_number * 104_729 + nonce * 1_000_003) % product
    choices: list[str] = []
    for options in axes:
        choices.append(options[ordinal % len(options)])
        ordinal //= len(options)
    return choices


def _diverse_scenario_text(
    *,
    category_number: int,
    category_name: str,
    scenario_number: int,
    nonce: int = 0,
) -> str:
    focus_options = _focus_options_for_category(category_name)
    (
        focus,
        service_bundle,
        tool_surface,
        operation,
        constraint,
        actor,
        output,
        stakeholder,
        cadence,
    ) = _mixed_radix_choices(
        (
            focus_options,
            _DIVERSE_SERVICE_BUNDLES,
            _DIVERSE_TOOL_SURFACES,
            _DIVERSE_OPERATIONS,
            _DIVERSE_CONSTRAINTS,
            _DIVERSE_ACTORS,
            _DIVERSE_OUTPUTS,
            _DIVERSE_STAKEHOLDERS,
            _DIVERSE_CADENCES,
        ),
        category_number=category_number,
        scenario_number=scenario_number,
        nonce=nonce,
    )
    return (
        f"{cadence}，{actor}需要在{category_name}中结合{service_bundle}和{tool_surface}，"
        f"围绕{focus}{operation}；{constraint}，并产出{output}给{stakeholder}"
    )


def _load_excluded_scenario_texts(sources: Sequence[Path]) -> set[str]:
    excluded: set[str] = set()
    for source in sources:
        if not source.is_file():
            continue
        excluded.update(
            scenario
            for _category_number, _category_name, _scenario_number, scenario in _parse_scenarios(
                source.read_text(encoding="utf-8")
            )
        )
    return excluded


def build_diverse_scenario_inventory(
    *,
    total_count: int,
    category_source: Path = DEFAULT_SOURCE,
    exclude_sources: Sequence[Path] = (),
) -> list[tuple[int, str, int, str]]:
    categories = _extended_diverse_categories(category_source)

    counts = _balanced_category_counts(total_count, sorted(categories))
    excluded = _load_excluded_scenario_texts(exclude_sources)
    seen = set(excluded)
    generated: list[tuple[int, str, int, str]] = []

    for category_number in sorted(categories):
        category_name = categories[category_number]
        for scenario_number in range(1, counts[category_number] + 1):
            nonce = 0
            while True:
                scenario = _diverse_scenario_text(
                    category_number=category_number,
                    category_name=category_name,
                    scenario_number=scenario_number,
                    nonce=nonce,
                )
                if scenario not in seen:
                    break
                nonce += 1
                if nonce > 10_000:
                    raise RuntimeError(
                        "unable to generate a unique diverse scenario for "
                        f"category {category_number}, scenario {scenario_number}"
                    )
            seen.add(scenario)
            generated.append((category_number, category_name, scenario_number, scenario))

    return generated


def _write_diverse_manifest(
    scenarios: Sequence[tuple[int, str, int, str]],
    output_dir: Path,
    *,
    category_source: Path,
    exclude_sources: Sequence[Path],
) -> Path:
    counts: dict[str, int] = {}
    for category_number, category_name, _scenario_number, _scenario in scenarios:
        counts[f"{category_number:03d}:{category_name}"] = counts.get(f"{category_number:03d}:{category_name}", 0) + 1
    source_category_count = len(_diverse_source_categories(category_source))
    configured_category_count = len(_extended_diverse_categories(category_source))
    manifest = {
        "ok": True,
        "generator": _DIVERSE_COVERAGE_PROFILE,
        "coverage_profile": _DIVERSE_COVERAGE_PROFILE,
        "coverage_axes": ["domain", "tool_surface"],
        "total_count": len(scenarios),
        "category_count": len(counts),
        "configured_category_count": configured_category_count,
        "source_category_count": source_category_count,
        "extra_domain_category_count": configured_category_count - source_category_count,
        "domain_sector_count": len(_EXTRA_DOMAIN_SECTORS),
        "domain_mode_count": len(_EXTRA_DOMAIN_MODES),
        "tool_surface_count": len(_DIVERSE_TOOL_SURFACES),
        "category_source": str(category_source),
        "exclude_sources": [str(source) for source in exclude_sources],
        "per_category_counts": counts,
        "output_dir": str(output_dir),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    return manifest_path


def generate(source: Path = DEFAULT_SOURCE, output_dir: Path = DEFAULT_OUTPUT_DIR) -> list[Path]:
    scenarios = _parse_scenarios(source.read_text(encoding="utf-8"))
    if not scenarios:
        raise ValueError(f"no scenarios found in {source}")
    return _write_scenarios(scenarios, output_dir)


def generate_combined(sources: Sequence[Path], output_dir: Path = COMBINED_DOUBLE_OUTPUT_DIR) -> list[Path]:
    scenario_sets: list[list[tuple[int, str, int, str]]] = []
    for source in sources:
        scenarios = _parse_scenarios(source.read_text(encoding="utf-8"))
        if not scenarios:
            raise ValueError(f"no scenarios found in {source}")
        scenario_sets.append(scenarios)
    return _write_scenarios(_combine_scenario_sets(scenario_sets), output_dir)


def generate_diverse(
    total_count: int = 100_000,
    *,
    category_source: Path = DEFAULT_SOURCE,
    output_dir: Path = DIVERSE_100K_OUTPUT_DIR,
    exclude_sources: Sequence[Path] = (),
) -> list[Path]:
    scenarios = build_diverse_scenario_inventory(
        total_count=total_count,
        category_source=category_source,
        exclude_sources=exclude_sources,
    )
    written = _write_scenarios(scenarios, output_dir)
    _write_diverse_manifest(
        scenarios,
        output_dir,
        category_source=category_source,
        exclude_sources=exclude_sources,
    )
    return written


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate one planner scenario text file per Markdown bullet.")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="Markdown scenario source file.")
    parser.add_argument(
        "--append-source",
        action="append",
        type=Path,
        default=[],
        help="Additional Markdown source to append by category into the same output directory.",
    )
    parser.add_argument(
        "--diverse-count",
        type=int,
        help="Generate a balanced deterministic diversity fabric with this many scenarios.",
    )
    parser.add_argument(
        "--exclude-source",
        action="append",
        type=Path,
        default=[],
        help="Markdown source whose scenario text must not be duplicated by --diverse-count output.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Generated scenario output root.")
    args = parser.parse_args(argv)

    if args.diverse_count is not None:
        if args.append_source:
            parser.error("--append-source cannot be combined with --diverse-count")
        default_exclude_sources = [
            source
            for source in (DEFAULT_SOURCE, EXPANSION_DOUBLE_SOURCE)
            if source.is_file()
        ]
        exclude_sources = args.exclude_source or default_exclude_sources
        written = generate_diverse(
            total_count=args.diverse_count,
            category_source=args.source,
            output_dir=args.output_dir,
            exclude_sources=exclude_sources,
        )
    else:
        sources = [args.source, *args.append_source]
        written = generate_combined(sources, args.output_dir) if args.append_source else generate(args.source, args.output_dir)
    print(f"wrote {len(written)} scenario files to {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
