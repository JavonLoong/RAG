# -*- coding: utf-8 -*-
"""把整合版接口说明写成尽量厚的 Markdown。"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OPENAPI = ROOT / "_openapi_current.json"
NAME = "PowerRAG技术链路与接口0923.md"
DESTS = [
    HERE / NAME,
    Path(r"D:\虚拟C盘") / NAME,
]

spec = importlib.util.spec_from_file_location("catalog", HERE / "做整合版技术链路与接口.py")
catalog = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(catalog)

FIELD_ZH = {
    "actor": "操作人。本机默认 local-user",
    "reviewer": "审核人姓名或角色",
    "decision": "审核结论：approve / reject / modify",
    "comment": "审核或操作说明",
    "corrections": "修改内容。改字段时必须同时带证据号",
    "expected_version": "乐观锁。对不上说明别人刚改过",
    "idempotency_key": "同一把钥匙重复提交，不当成两次",
    "document_id": "资料编号，同一份资料多个版本共用",
    "source_name": "原始文件名",
    "content_base64": "文件字节的 Base64",
    "chunk_size": "切块长度",
    "overlap": "相邻块重叠字数",
    "parser_backend": "解析器：auto / native / deepdoc / mineru / docling / unstructured",
    "use_ocr": "识图取字：auto / always / never",
    "translation_target": "要不要翻译成 zh 或 en",
    "auto_run_ocr": "解析后是否自动跑识图",
    "ocr_page_timeout_seconds": "单页识图超时秒数",
    "metadata": "附加元数据",
    "pages": "按页的识图结果",
    "project_id": "项目编号",
    "name": "显示名",
    "description": "说明",
    "domain": "领域，默认 gas_turbine",
    "created_by": "创建人",
    "configuration": "项目配置",
    "data_policy": "资料策略",
    "acceptance": "验收配置",
    "question": "问句",
    "collection": "检索集合名",
    "top_k": "最多返回几条",
    "mode": "问答或检索模式",
    "statements": "图谱关系列表，每条必须带 evidence_ids",
    "source_document_version_ids": "构图用的已发布资料版本",
    "graph_version_id": "图谱版本号",
    "document_version_ids": "出表用的资料版本",
    "template": "出表模板，例如 gas_turbine_minimum_v1",
    "requested_by": "谁发起出表",
    "format": "导出格式 json / csv / docx",
    "background": "true 时后台跑，立刻返回任务号",
    "limit": "最多返回几条",
    "q": "检索词",
    "session_id": "对话编号",
    "llm_api_key": "模型钥匙。现网治理路径尽量不走这一项",
    "graph_db_path": "图库 SQLite 路径",
    "filename": "文件名",
    "filenames": "文件名列表",
    "reason": "原因",
    "assignee": "指派人",
    "message": "评论正文",
    "task_ids": "任务号列表",
    "worker_id": "后台工人编号",
    "progress": "0 到 1 的进度",
    "gate_id": "验收门禁编号",
    "artifact_key": "验收材料键",
    "payload": "正文或材料内容",
    "evidence_ids": "证据号列表，必须能打开原页",
    "subject": "关系主语",
    "predicate": "关系",
    "object": "关系宾语",
    "subject_type": "主语类型，必须在已批准规则里",
    "object_type": "宾语类型，必须在已批准规则里",
    "confidence": "抽取把握，0 到 1",
    "status": "状态",
    "title": "标题",
    "role": "消息角色 user / assistant / system",
    "content": "正文",
}

FAMILY_INTRO = {
    "打开与文档": (
        "这一组不改业务数据。浏览器打开 `/` 就是工作台。"
        "`/api/health` 用来确认进程还活着，返回里有版本号 2.1.0。"
        "`/docs`、`/redoc`、`/openapi.json` 是同一份接口的三种看法：点着试、排版读、给程序读。"
        "权威清单以正在跑的服务为准，本文件按 2026-09-23 实扫写成。"
    ),
    "工作台入库检索": (
        "对应界面 M1。文件先 `POST /api/upload` 落到上传目录，再 `POST /api/process` 或 `POST /api/ingest` 切块、向量化、写入 Chroma。"
        "`/api/search` 只找段落，`/api/query` 会组答案：能走图就沿边，图不够就退回普通检索。"
        "这是快路径，不管治理库里的审核发布。要页码证据、版本、回滚，走后面的 `/api/delivery`。"
        "集合默认 `power_equipment`。导出、删集合、看日志、跑评测都在这一组。"
    ),
    "检索策略与登录": (
        "管“谁能搜哪一类资料”。策略本身也有草案、批准、推正式、退回，和资料版本一样留痕。"
        "角色、通知人、人员目录、身份源、会话、密钥轮换都在这里。"
        "单机演示可以不配身份源。一旦配了，检索前要先有有效会话。"
        "前缀一律 `/api/retrieval/policies`。"
    ),
    "交付 · 项目与任务": (
        "治理链路的外壳。先有项目，才有资料版本、图、出表。"
        "项目能按模板复制、整包导出、整包恢复。恢复会核哈希，空文件也按 0 字节认，不再误判丢失。"
        "图谱规则和出表模板按项目登记，批准后才能用。"
        "模型提供方写在项目上，健康检查单独看。治理路径也可以不配钥匙，由调用方自己把关系、字段填进来。"
        "后台任务有心跳、取消、重试、指派、评论。待审队列和原始页图也挂在这一组边上。"
    ),
    "交付 · 资料": (
        "治理链路的第一段：解析 → 候选 → 整页审 → 发布 → 检索投影。"
        "入口是 `POST /api/delivery/documents/intake`：文件变 Base64 进来，按页切块，保住页码、标题、表、图注。"
        "扫描件走识图。缺页、低把握、版面乱，记成待审问题，不偷偷入库。"
        "人可以改稿出新版本。对照两个版本。发布后才能被构图和检索正式使用。"
        "回滚按资料号退到旧正式版。索引可重建。证据号能直接开到原页。"
        "界面 M4 资料台账主要打这一组。"
    ),
    "交付 · 图谱": (
        "只吃已发布资料。候选关系必须带 `evidence_ids`，且证据落在所选版本的页上。"
        "类型、关系不在已批准规则里，不能发布。缺证据、证据跑到别的版本，也不能发布。"
        "`POST /graphs/candidates` 是把已经写好的关系交进去校验、落库。"
        "`POST /graphs/extract` 是服务端抽，需要已登记提供方；没配钥匙时，由调用方读正文自己写 `statements`。"
        "发布后可同步进 GraphStore，供沿边问答。也能对照普通检索、查路径、导出三元组、退回旧图。"
    ),
    "交付 · 出表": (
        "只吃已发布图。生成设备、部件、故障、原因、后果、探测、措施。"
        "对不上的字段保持空，并挂证据号。没有批准的评分政策，不写严重度、频度、探测度，不编风险优先数。"
        "逐字段审、整表审、发布、导出 JSON / CSV / DOCX，三份行数必须一致。"
        "反馈要指回上游是资料、图还是模板。记下反馈和真的重跑上游，不是同一件事。"
    ),
    "交付 · 验收": (
        "对应界面 M5。门禁材料、候选稿、截图附件、验收包、交接说明。"
        "写材料要带当前哈希，对不上就是别人刚改过。"
        "门禁没齐时，验收包仍能生成，总状态不会写成通过。"
        "需要验收管理员身份。"
    ),
    "运行图与质检": (
        "对应界面 M2 / M3 边上的运行图库：导入浏览器里画的图、社区划分、社区摘要、全局问答、导出、清空。"
        "社区摘要和全局问答要模型钥匙。"
        "质检记录问答质量，可审、可升成回归题。"
        "和 `/api/delivery/graphs` 不是同一套：那边有版本和审核，这边是运行投影。"
    ),
    "对话记忆": (
        "多轮问答的会话、消息、上下文。"
        "近期消息加摘要，给 `/api/query` 当上文。"
        "删消息或删会话会连带清向量侧写。"
    ),
    "版本化问答": (
        "稳定合同的问答。`/api/v1/query` 一次返回，`/api/v1/query/stream` 按事件往外推。"
        "错误用统一信封：工作区不存在、索引未就绪、模式不可用、模型不可用。"
        "和 `/api/query` 并列，给要固定字段的调用方。"
    ),
    "出表治理 v1": (
        "另一条出表线，前缀 `/api/v1/fmea`。"
        "管分析稿修订、审批、发布、撤回、替换，模板草稿和补丁，迁移试跑，导出行，逐行审核建议，风险分确认，故障传播路径，分析范围建议。"
        "和工作台 `/api/delivery/fmea` 并行：那边跟已发布图绑得紧，这边把修订和发布生命周期拆得更细。"
        "界面里的 FMEA 子页主要打这一组。"
    ),
}

MORE: dict[tuple[str, str], str] = {
    ("GET", "/api/delivery/documents"): (
        "列出当前项目里的资料版本：候选、待审、已发布、已退役。"
        "每条带版本号、页数、质量问题、最近一次审核。"
        "界面台账刷新就打这一条。可按项目、状态分页。"
    ),
    ("POST", "/api/delivery/documents-index/rebuild"): (
        "按已发布资料重做检索投影。改过切块、换过向量、发布过新版之后打。"
        "可带 background=true，立刻回任务号，避免浏览器卡住。"
        "没发布的候选不会进正式索引。"
    ),
    ("GET", "/api/delivery/documents-index/status"): (
        "看索引是否跟上已发布版本：集合名、条数、是否在重建、上次成功时间。"
        "检索结果和台账对不上时先看这里。"
    ),
    ("GET", "/api/delivery/documents-search"): (
        "只在已发布资料里搜。query 参数 q 是问句，mode 可选关键词、语义、混合，top_k 默认 10。"
        "命中带块号和页码，能再打 open 回到原页。"
        "未发布稿搜不到，这是故意的。"
    ),
    ("POST", "/api/delivery/documents/batch-review"): (
        "一次审多份。每份仍要审核人、结论、意见。"
        "有一份缺证据或结论不合法，整批按治理错误退回，不会只成功一半还不记账。"
    ),
    ("GET", "/api/delivery/documents/compare/{left_id}/{right_id}"): (
        "对照两个版本的正文、页、块、质量问题。"
        "改稿前后、回滚前都看这一条。左右都是版本号，不是资料号。"
    ),
    ("POST", "/api/delivery/documents/intake"): (
        "治理解析入口。文件变 Base64 进来，选出解析器，切块，生成候选版本和证据号。"
        "chunk_size 默认 500，overlap 默认 50。parser_backend 默认 auto。"
        "扫描件会挂识图任务。缺页、低把握、表被拍扁，写成质量问题，状态停在待审，不会直接变正式版。"
    ),
    ("POST", "/api/delivery/documents/intake/ocr-result"): (
        "把按页识图结果写回候选稿。缺页、空白、低把握、版面风险高，都留成待审，不按成功入库。"
        "pages 至少一页。可带 expected_pages、失败页、超时页，方便对账。"
    ),
    ("GET", "/api/delivery/documents/ocr-jobs/{job_id}"): (
        "看识图任务：哪些页成功、失败、超时，把握分布，能不能重试。"
        "界面上“重试失败页”先读这一条。"
    ),
    ("POST", "/api/delivery/documents/ocr-jobs/{job_id}/retry-pages"): (
        "只重跑指定页，已成功的页不动。要带页号列表和幂等钥匙。"
        "仍失败就继续记问题，不会假装过了。"
    ),
    ("POST", "/api/delivery/documents/ocr-jobs/{job_id}/run"): (
        "启动或继续跑识图。本机有引擎就用本机；没有且页图已经在上下文里，可以由调用方自己认字再回写 ocr-result。"
        "不要为了这一步去要云端识图钥匙。"
    ),
    ("GET", "/api/delivery/documents/source-assets/{asset_id}/pages/{page}"): (
        "取出某一页原图或渲染页，给整页对照。"
        "DOCX 精确页依赖本机 Office 或 LibreOffice。页号从 1 起。"
    ),
    ("POST", "/api/delivery/documents/{document_id}/rollback"): (
        "按资料号退回上一个正式版。候选稿不会被选成正式版。"
        "回滚后索引和下游图、表都可能过期，要重发布或重同步。"
    ),
    ("GET", "/api/delivery/documents/{version_id}"): (
        "读一个版本的全文块、页定位、质量问题、审核历史、是否已发布。"
        "构图前先确认状态是 published。"
    ),
    ("POST", "/api/delivery/documents/{version_id}/publish"): (
        "把已批准的候选变成正式版。没有证据或最近一次审核不是批准，会被拒绝。"
        "发布后才允许构图和正式检索。可带 comment、idempotency_key。"
    ),
    ("POST", "/api/delivery/documents/{version_id}/review"): (
        "对人可见的候选下结论：批准、驳回、改完再来。"
        "改了正文要走 revise 出新版本，不要只在评论里改。"
        "必须带审核人。结论会进治理库。"
    ),
    ("GET", "/api/delivery/documents/{version_id}/review-package"): (
        "给整页对照：原页、解析块、质量问题。可带 page 只取一页。"
        "界面“进入整页审核”打这一条。大文件可能较慢。"
    ),
    ("POST", "/api/delivery/documents/{version_id}/revise"): (
        "在已有版本上改稿，生成新版本号，旧版保留可对照。"
        "改过的块要能指回原页。新版仍是候选，还要再审再发。"
    ),
    ("GET", "/api/delivery/evidence/{evidence_id}/open"): (
        "凭证据号打开资料版本、页、块、原文摘录。"
        "图上的边、表上的字段，最后都要能打到这一条。打不开就说明绑证据断了。"
    ),
}


def load_openapi() -> dict:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


def deref(schema: dict, components: dict, depth: int = 0) -> dict:
    if not isinstance(schema, dict) or depth > 8:
        return schema or {}
    ref = schema.get("$ref")
    if ref:
        name = str(ref).rsplit("/", 1)[-1]
        target = (components.get("schemas") or {}).get(name) or {}
        merged = dict(target)
        for key, value in schema.items():
            if key != "$ref":
                merged[key] = value
        return deref(merged, components, depth + 1)
    if "allOf" in schema:
        out: dict = {"properties": {}, "required": []}
        for part in schema["allOf"]:
            resolved = deref(part, components, depth + 1)
            out["properties"].update(resolved.get("properties") or {})
            out["required"].extend(resolved.get("required") or [])
            if resolved.get("description") and not out.get("description"):
                out["description"] = resolved["description"]
        out.update({k: v for k, v in schema.items() if k != "allOf"})
        return out
    if "anyOf" in schema or "oneOf" in schema:
        options = schema.get("anyOf") or schema.get("oneOf") or []
        non_null = [deref(item, components, depth + 1) for item in options if item.get("type") != "null"]
        if len(non_null) == 1:
            chosen = dict(non_null[0])
            chosen["nullable"] = True
            return chosen
    return schema


def type_of(schema: dict) -> str:
    if schema.get("enum"):
        return " / ".join(str(item) for item in schema["enum"][:8])
    if schema.get("type"):
        return str(schema["type"])
    if schema.get("anyOf") or schema.get("oneOf"):
        return "可选类型"
    if schema.get("items"):
        return "array"
    return "object"


def field_lines(schema: dict, components: dict) -> list[str]:
    resolved = deref(schema, components)
    props = resolved.get("properties") or {}
    required = set(resolved.get("required") or [])
    lines = []
    for name, raw in props.items():
        spec = deref(raw, components)
        mark = "必填" if name in required else "可选"
        default = spec.get("default", raw.get("default"))
        extra = FIELD_ZH.get(name, spec.get("description") or raw.get("description") or "")
        bits = [f"`{name}`", type_of(spec), mark]
        if default is not None and default != "":
            bits.append(f"默认 `{default}`")
        if spec.get("minimum") is not None:
            bits.append(f"最小 {spec['minimum']}")
        if spec.get("maximum") is not None:
            bits.append(f"最大 {spec['maximum']}")
        if extra:
            bits.append(str(extra).replace("\n", " "))
        lines.append("- " + "，".join(bits))
    return lines


def op_of(openapi: dict, method: str, path: str) -> dict:
    path_item = (openapi.get("paths") or {}).get(path) or {}
    return path_item.get(method.lower()) or {}


def param_lines(op: dict, components: dict, where: str) -> list[str]:
    lines = []
    for param in op.get("parameters") or []:
        if param.get("in") != where:
            continue
        schema = deref(param.get("schema") or {}, components)
        mark = "必填" if param.get("required") else "可选"
        extra = FIELD_ZH.get(param.get("name", ""), param.get("description") or "")
        default = schema.get("default")
        bit = f"- `{param.get('name')}` {type_of(schema)} {mark}"
        if default is not None:
            bit += f"，默认 `{default}`"
        if extra:
            bit += f"，{extra}"
        lines.append(bit)
    return lines


def body_schema(op: dict) -> dict:
    content = ((op.get("requestBody") or {}).get("content") or {})
    for key in ("application/json", "multipart/form-data", "application/x-www-form-urlencoded"):
        if key in content:
            return content[key].get("schema") or {}
    if content:
        return next(iter(content.values())).get("schema") or {}
    return {}


def response_lines(op: dict) -> list[str]:
    lines = []
    for code, item in (op.get("responses") or {}).items():
        desc = (item or {}).get("description") or ""
        if str(code).startswith("2"):
            meaning = "成功"
        elif code == "422":
            meaning = "参数不合法"
        elif code == "404":
            meaning = "找不到"
        elif code == "409":
            meaning = "版本冲突或状态不允许"
        elif code == "413":
            meaning = "太大"
        elif code == "415":
            meaning = "类型不支持"
        elif code == "503":
            meaning = "模型或依赖不可用"
        else:
            meaning = "失败"
        text = f"- `{code}` {meaning}"
        if desc and desc not in {"Successful Response", "Validation Error"} and not looks_english(desc):
            text += f"。{desc}"
        lines.append(text)
    return lines or ["- 以实际返回为准"]


def looks_english(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    if len(letters) < 8:
        return False
    ascii_letters = sum(1 for c in letters if ord(c) < 128)
    return ascii_letters / len(letters) > 0.85


def response_field_blocks(op: dict, components: dict) -> list[str]:
    blocks: list[str] = []
    for code, item in (op.get("responses") or {}).items():
        if not str(code).startswith("2"):
            continue
        content = (item or {}).get("content") or {}
        if not content:
            continue
        for media, spec in content.items():
            schema = (spec or {}).get("schema") or {}
            resolved = deref(schema, components)
            if media.startswith("application/json") or media.endswith("+json"):
                fields = field_lines(schema, components)
                if not fields and resolved.get("type") == "array":
                    item_schema = deref(resolved.get("items") or {}, components)
                    item_fields = field_lines(item_schema, components)
                    if item_fields:
                        blocks.append(f"**返回体**  `{code}` JSON 数组，元素字段：")
                        blocks.extend(item_fields)
                        continue
                if fields:
                    blocks.append(f"**返回体字段**  `{code}` `{media}`")
                    blocks.extend(fields)
                elif resolved.get("additionalProperties") or resolved.get("type") in {None, "object"}:
                    blocks.append(f"**返回体**  `{code}` JSON 对象，字段以 `/openapi.json` 该条为准。")
            elif media.startswith("text/"):
                blocks.append(f"**返回体**  `{code}` 文本 `{media}`。")
            else:
                blocks.append(f"**返回体**  `{code}` 二进制 `{media}`，浏览器直接下载或预览。")
    return blocks


def when_text(method: str, path: str) -> str:
    if path in {"/", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}:
        return "打开工作台或查接口合同时用。"
    if path == "/api/health":
        return "启动后先打这一条，确认端口和版本。"
    if path.startswith("/api/delivery/acceptance"):
        return "核门禁、交材料、打验收包时用。"
    if "upload" in path and method == "POST":
        return "手里有文件、还没进解析时用。"
    if path.endswith("/intake"):
        return "文件要变成带页码候选稿时用。这是治理解析的正门。"
    if "ocr" in path:
        return "扫描件或低质量页需要认字、重试、对原页时用。"
    if path.endswith("/review") or "review-package" in path or "statement-reviews" in path or "field-reviews" in path:
        return "人要下结论或看对照材料时用。没审过不能发布。"
    if path.endswith("/publish"):
        return "审核已通过，要把候选变成正式版时用。"
    if "rollback" in path:
        return "正式版有问题、要退回旧正式版时用。"
    if "compare-rag" in path:
        return "同一题对照沿图回答和普通检索时用。"
    if "compare" in path:
        return "两个版本要并排看差异时用。"
    if "rebuild" in path or path.endswith("/resync"):
        return "正式版已变、检索库或图库还停在旧投影时用。"
    if path.startswith("/api/delivery/graphs") and ("candidates" in path or path.endswith("/extract")):
        return "已发布资料要抽成关系时用。关系必须能回到原页。"
    if "/fmea/tasks" in path and method == "POST" and path.endswith("/tasks"):
        return "已发布图要出故障分析表时用。"
    if "export" in path:
        return "要把正式结果拿出去时用。未发布通常不给正式文件。"
    if path.startswith("/api/query") or path.startswith("/api/v1/query") or path.endswith("/search") or path.endswith("/query"):
        return "已经有可检索资料或已发布图，要提问时用。"
    if path.startswith("/api/memory"):
        return "问答要带着上一轮上下文时用。"
    if "policies" in path:
        return "要改谁能检索、通知谁、如何登录时用。"
    if method == "GET":
        return "只看现状，不改正式版本。"
    if method == "DELETE":
        return "确认要删对象时用。不可恢复的要先导出。"
    return "按界面按钮或脚本编排调用。"


def constraint_text(method: str, path: str) -> str:
    bits = []
    if path.startswith("/api/delivery"):
        bits.append("操作人默认 `local-user`，可在请求体 `actor` / `reviewer` 或请求头里改。")
    if "publish" in path:
        bits.append("最近一次审核必须是批准，且证据还在。")
    if "/graphs/" in path and "candidates" in path or path.endswith("/extract"):
        bits.append("源资料必须已发布。关系类型必须在已批准规则里。")
    if "/fmea/tasks" in path and method == "POST" and path.endswith("/tasks"):
        bits.append("图谱必须已发布。对不上的字段保持空，不编评分。")
    if "ocr" in path:
        bits.append("失败页要留下来给人看，不能当成成功入库。")
    if path.startswith("/api/delivery/acceptance"):
        bits.append("需要验收管理员。改材料必须带当前哈希。")
    if "llm_api_key" in path or "community/summarize" in path or "search/global" in path:
        bits.append("这条要模型钥匙。治理主路径可以不走它。")
    if not bits:
        bits.append("参数不合法返回 422。对象不存在返回 404。状态不允许返回 409。")
    return "".join(bits)


def example_block(method: str, path: str) -> str:
    if path == "/api/delivery/documents/intake":
        return (
            "```json\n"
            "{\n"
            '  "document_id": "manual-001",\n'
            '  "source_name": "lube-oil-filter.pdf",\n'
            '  "content_base64": "<文件字节>",\n'
            '  "chunk_size": 800,\n'
            '  "overlap": 100\n'
            "}\n"
            "```\n"
        )
    if path == "/api/delivery/graphs/candidates":
        return (
            "```json\n"
            "{\n"
            '  "source_document_version_ids": ["manual-001:v1"],\n'
            '  "statements": [\n'
            "    {\n"
            '      "subject": "润滑油系统",\n'
            '      "predicate": "故障模式",\n'
            '      "object": "过滤器堵塞",\n'
            '      "subject_type": "COMPONENT",\n'
            '      "object_type": "FAILURE_MODE",\n'
            '      "evidence_ids": ["EV-..."],\n'
            '      "confidence": 0.9\n'
            "    }\n"
            "  ]\n"
            "}\n"
            "```\n"
        )
    if path == "/api/delivery/fmea/tasks" and method == "POST":
        return (
            "```json\n"
            "{\n"
            '  "requested_by": "reviewer",\n'
            '  "graph_version_id": "graph:v1",\n'
            '  "document_version_ids": ["manual-001:v1"],\n'
            '  "template": "gas_turbine_minimum_v1"\n'
            "}\n"
            "```\n"
        )
    if path.endswith("/review") and path.startswith("/api/delivery/documents/"):
        return (
            "```json\n"
            "{\n"
            '  "reviewer": "domain-expert",\n'
            '  "decision": "approve",\n'
            '  "comment": "页码和关键字段已对照原页"\n'
            "}\n"
            "```\n"
        )
    return ""


def heading_id(method: str, path: str) -> str:
    raw = f"{method.lower()}-{path.strip('/').replace('/', '-').replace('{', '').replace('}', '').replace(':', '')}"
    return raw[:80]


def render_endpoint(method: str, path: str, name: str, openapi: dict) -> str:
    components = openapi.get("components") or {}
    op = op_of(openapi, method, path)
    desc = catalog.describe(method, path, name)
    more = MORE.get((method, path), "")
    summary = (op.get("description") or op.get("summary") or "").strip()
    parts = [f"### `{method} {path}`", ""]
    parts.append(f"**做什么**  {desc}")
    if more:
        parts.append("")
        parts.append(more)
    if (
        summary
        and summary.lower() not in {desc.lower(), name.replace("_", " ")}
        and not looks_english(summary)
    ):
        parts.append("")
        parts.append(summary.replace("\n", " "))
    parts.append("")
    parts.append(f"**何时用**  {when_text(method, path)}")
    parts.append("")
    path_params = param_lines(op, components, "path")
    query_params = param_lines(op, components, "query")
    header_params = param_lines(op, components, "header")
    if path_params:
        parts.append("**路径参数**")
        parts.extend(path_params)
        parts.append("")
    if query_params:
        parts.append("**查询参数**")
        parts.extend(query_params)
        parts.append("")
    if header_params:
        parts.append("**请求头**")
        parts.extend(header_params)
        parts.append("")
    body = body_schema(op)
    fields = field_lines(body, components) if body else []
    if fields:
        parts.append("**请求体字段**")
        parts.extend(fields)
        parts.append("")
    elif (op.get("requestBody") or {}).get("required"):
        parts.append("**请求体**  需要正文，字段以 `/openapi.json` 为准。")
        parts.append("")
    example = example_block(method, path)
    if example:
        parts.append("**请求示例**")
        parts.append("")
        parts.append(example)
    parts.append("**返回**")
    parts.extend(response_lines(op))
    parts.append("")
    body_fields = response_field_blocks(op, components)
    if body_fields:
        parts.extend(body_fields)
        parts.append("")
    parts.append(f"**约束**  {constraint_text(method, path)}")
    parts.append("")
    return "\n".join(parts)


def front_matter(routes: list[tuple[str, str, str]]) -> str:
    toc = ["- [项目是什么](#项目是什么)", "- [怎么打开](#怎么打开)", "- [仓库分层](#仓库分层)",
           "- [两套编号](#两套编号)", "- [全项目一条线](#全项目一条线)", "- [三套库为什么分开](#三套库为什么分开)",
           "- [界面五页怎么对接口](#界面五页怎么对接口)", "- [典型调用顺序](#典型调用顺序)",
           "- [怎么调接口](#怎么调接口)",
           "- [先走哪条链路](#先走哪条链路)",
           "- [Skill 和模型槽](#skill-和模型槽)",
           "- [部署与运行时](#部署与运行时)",
           "- [共享对象](#共享对象)",
           "- [治理库表](#治理库表)",
           "- [出表字段和图谱最小链](#出表字段和图谱最小链)",
           "- [HTTP 状态](#http-状态)",
           "- [有内容就不能直接删](#有内容就不能直接删)",
           "- [程序目录清单](#程序目录清单)",
           "- [界面全部页面](#界面全部页面)",
           "- [作废撤回和删除怎么留痕](#作废撤回和删除怎么留痕)",
           "- [现网全部接口](#现网全部接口)"]
    for title, _ in catalog.FAMILIES:
        toc.append(f"  - [{title}](#{title.replace(' ', '-').replace('·', '').replace('（', '').replace('）', '')})")
    toc.append("- [受控失败](#受控失败)")
    toc.append("- [术语](#术语)")
    head = f"""# PowerRAG 技术链路与接口

日期：2026-09-23  
独立文件：`D:\\虚拟C盘\\PowerRAG技术链路与接口0923.md`  
现网入口：`http://127.0.0.1:8000`  
接口文档：`http://127.0.0.1:8000/docs`  
权威清单：`http://127.0.0.1:8000/openapi.json`  
实扫条数：**{len(routes)}**（`api_server/current_console` 的 `create_app`，应用版本 2.1.0）  
本文按现网 OpenAPI 展开请求字段和成功返回体。服务以后如果改了合同，以正在跑的 `/openapi.json` 为准。

目录

{chr(10).join(toc)}

## 项目是什么

PowerRAG 是面向燃气轮机和动力装备资料的**本地**工作台。手册、扫描件、表格进来以后，先读成带页码的证据，再检索、构图、问答，最后出可审核的故障分析表。

产品就是这一个工作台。浏览器打开。不是多租户网上服务。仓库里的 Electron 目录只保留，现网不启动、不打包、不演示。Windows 可执行文件 `PowerRAG.exe` 只是把同一套 FastAPI 拉起来，再打开系统浏览器。

相对“把整本资料丢给大模型让它直接答”，这里多了一条硬约束：**图上的关系和表上的字段必须能回到手册页码**。回不到原页，就不能当正式结论发布。百科里成立、书里没写的事，只能标成书中未记载，不能写进图。

`RAG交付/` 是历史快照，接口是子集，不是现网。现网入口只有 `api_server/current_console`。

## 怎么打开

1. 客户包：拷贝 `desktop_launcher/dist/PowerRAG/` 整个目录（必须带 `_internal`），双击 `PowerRAG.exe`。关掉状态窗口即停服务。默认 `http://127.0.0.1:8000`，端口被占用时看状态窗口。
2. 源码：在仓库根目录执行 `python api_server/current_console/server.py`，或双击 `api_server/current_console/start_local.bat`。
3. 数据目录：向量库、上传、日志在 `%LOCALAPPDATA%\\PowerRAG\\current_console\\`（`chroma` / `uploads` / `logs`）。可执行文件不会另起第二套库。

## 仓库分层

| 层 | 目录 | 管什么 | 和接口的关系 |
|---|---|---|---|
| 界面 | `frontend_app/current_console` | 五页工作台、抽屉、整页审核 | 浏览器只打下面这些 HTTP |
| 接口 | `api_server/current_console` | FastAPI，现网 {len(routes)} 条 | `/api/*` 全部挂在这里 |
| 解析 | `data_pipeline` | 读 PDF / DOCX / 图，识图取字，保住页码和表 | `/api/process`、`/api/delivery/documents/intake` |
| 入库 | `knowledge_base`、`storage_layer` | 正式版本、切块、向量、治理账本 | `/api/ingest`、`/api/delivery/documents*` |
| 图谱 | `kg_pipeline`、`storage_layer/graph_store.py` | 抽关系、社区、运行图库 | `/api/delivery/graphs*`、`/api/graphrag*` |
| 问答 | `rag_orchestrator` | 普通检索、沿边回答、对照、拒绝空答 | `/api/query`、`/api/v1/query`、图上的 `/query` |
| 出表 | `rag_orchestrator/fmea.py`、`fmea_application`、`fmea_infrastructure` | 从已发布图出表，导出 Office | `/api/delivery/fmea*`、`/api/v1/fmea*` |
| 验收 | `evaluation` | 门禁材料、金标、验收包 | `/api/delivery/acceptance*` |
| 启动 | `desktop_launcher` | Windows 可执行文件 | 不新增接口，只拉起 :8000 |

## 两套编号

界面从左到右是值班流水线：

1. **M1 资料接入**：上传、解析、写入检索库。
2. **M2 知识组织**：构图、社区、导入导出运行图。
3. **M3 图谱问答**：提问、多轮、对照。
4. **M4 可信交付**：项目、审核、发布、出表。这是治理全段的操作台。
5. **M5 验收**：门禁材料和验收包。

交付治理是另一套，按证据状态往下传，**后一段只吃前一段已经发布的结果**：

1. **解析**：文件 → 带页码的块和证据号。
2. **入库**：审核通过才成为正式资料，并投影到检索。
3. **构图**：只从正式资料抽关系，每条绑回原页。
4. **出表**：只从正式图生成故障分析表，每个字段带证据。

不要把界面 M2 和治理“解析”当成同一个东西。界面 M4 才覆盖治理的解析到出表。界面 M5 不是出表，是验收台。

## 全项目一条线

```mermaid
flowchart LR
  A[资料进来] --> B[读成带页码的证据]
  B --> C[人审]
  C --> D[正式入库]
  D --> E[只从已发布资料构图]
  E --> F[检索或沿图问答]
  E --> G[只从已发布图出表]
  G --> H[验收整包]
  D --> I[回滚或对照旧版]
  E --> I
```

1. **进来。** 工作台 `POST /api/upload` 只落盘；治理 `POST /api/delivery/projects/{{id}}/documents/upload` 或 `POST /api/delivery/documents/intake` 会生成候选版本。
2. **读成证据。** 原生 PDF、DOCX 走文本和结构；扫描件走识图。页、块、表、图注都要能定位。缺页、低把握写成质量问题。
3. **人看原页。** `review-package` 把原页和解析放在同一屏。结论写入治理库。改了正文必须 `revise` 出新版本。
4. **发布。** 没有批准不能发布。发布后才允许正式检索和构图。
5. **构图。** `statements` 必须带 `evidence_ids`。类型或关系不在规则里、证据不在所选版本，不能发布图。
6. **问答。** 关键词检索、沿已发布图、同一题对照。原文没有的要能拒绝，不能靠模型补书中没有的情节。
7. **出表。** 设备、故障、原因、措施来自已发布图。空着比编造好。导出三份行数一致。
8. **验收。** 门禁材料、截图、整包。没齐就如实写没齐。
9. **整包进出。** 项目可导出、可恢复。哈希对不上不能装成成功恢复。

## 三套库为什么分开

| 库 | 实现 | 记什么 | 不记什么 |
|---|---|---|---|
| 治理库 | SQLite `GovernanceStore` | 版本、审核、证据号、出表任务、反馈 | 不直接回答问题 |
| 向量库 | Chroma | 已发布或工作台入库的切块向量 | 不代替审核账本 |
| 图库 | SQLite `GraphStore` | 已同步的点和边，供沿边检索 | 没有审核意见 |

发布资料 **不会自动** 保证图库已更新；发布图之后要看是否 `resync`。建一条反馈 **不等于** 已经重跑解析。兼容的导出形状不等于两条链路已经接通，要以实际调用为准。

## 界面五页怎么对接口

| 页 | 人在做什么 | 主要接口 |
|---|---|---|
| M1 资料接入 | 选文件、看进度、写入检索库 | `/api/upload` `/api/uploads` `/api/process` `/api/ingest` `/api/search` `/api/logs` |
| M2 知识组织 | 看图、社区、导入导出 | `/api/graphrag/import` `/community/detect` `/export` `/reset` |
| M3 图谱问答 | 提问、看依据、多轮 | `/api/query` `/api/v1/query` `/api/memory/sessions*` `/api/graphrag/search/global` |
| M4 可信交付 | 建项目、审资料、发图、出表 | `/api/delivery/projects*` `/documents*` `/graphs*` `/fmea*` `/tasks*` |
| M5 验收 | 看门禁、传截图、打验收包 | `/api/delivery/acceptance/*` |
| 抽屉 · 总览 | 看是否健康 | `/api/health` `/api/stats` |
| 抽屉 · 设置 | 集合、策略、身份、日志 | `/api/retrieval/policies*` `/api/collections/{{name}}` `/api/logs` |

`#page-search`、`#page-kg` 还在 HTML 里，不挂进现网导航，不要当成正式入口。

## 典型调用顺序

治理主路径，按这个顺序打，中间缺一步，后面应被拒绝：

1. `POST /api/delivery/projects` 建项目。
2. `POST /api/delivery/projects/{{id}}/documents/upload` 或 `POST /api/delivery/documents/intake` 进候选。
3. 如需识图：`POST .../ocr-jobs/{{id}}/run`，失败页 `retry-pages`。
4. `GET .../documents/{{version}}/review-package` 对照原页。
5. `POST .../documents/{{version}}/review`，结论 `approve`。
6. `POST .../documents/{{version}}/publish`。
7. `POST /api/delivery/graphs/candidates` 提交带证据的关系；或 `POST /graphs/extract`。
8. `POST .../graphs/{{id}}/review` → `publish` → 需要的话 `resync`。
9. `POST /api/delivery/fmea/tasks` → 逐字段审 → `publish` → `export`。
10. 出问题：`feedback` 然后 `remediate`，不要只留一条评论。
11. 要带走：`POST /api/delivery/projects/{{id}}/export-package`；换机器 `POST /projects/restore`。

工作台快路径可以只走 `/api/upload` → `/api/process` → `/api/query`。这条快，但没有治理发布账本，不能当成“已经正式入库”。

## 怎么调接口

- 根地址：`http://127.0.0.1:8000`
- JSON：`Content-Type: application/json`
- 上传文件：`multipart/form-data`
- 治理操作人：请求体 `actor` / `reviewer`，默认 `local-user`
- 后台：查询参数 `background=true`，用任务号轮询 `/api/delivery/tasks/{{id}}`
- 交互文档：`/docs` 可直接试
- 下面每一条都尽量写清：做什么、何时用、路径参数、查询参数、请求体字段、返回码、返回体字段、约束。没有请求体的 GET 会略过请求体段。字段中文来自常见字段表，其余跟 OpenAPI 走。
"""
    return head + extra_complete()


def extra_complete() -> str:
    return """
## 先走哪条链路

客户演示和正式交付只认这一条：

`/api/delivery`：建项目 → 解析进候选 → 整页审 → 发布资料 → 带证据构图 → 审图发布 → 需要时 `resync` → 出故障分析表 → 导出 JSON / CSV / DOCX → 验收包。

其余都是旁边的能力，不要和主路径混成“已经正式入库”。

| 你要做的事 | 走这条 | 不要当成 |
|---|---|---|
| 正式解析、页码、审核、回滚 | `/api/delivery/documents*` | `/api/upload` + `/api/process` |
| 正式图谱、证据边、发布 | `/api/delivery/graphs*` | `/api/graphrag/import` 运行图 |
| 正式故障分析表（跟已发布图绑） | `/api/delivery/fmea*` | 只有 `/api/v1/fmea*` 的修订生命周期 |
| 工作台先看一眼能不能搜 | `/api/upload` → `/api/process` → `/api/query` | 正式验收证据 |
| 浏览器里画的运行图、社区、全局问答 | `/api/graphrag*` | 治理库里的图谱版本 |
| 出表治理 v1 子页：修订、撤回、替换、风险、传播 | `/api/v1/fmea*`、`/fmea.html` | 工作台 M4 出表的唯一入口 |
| 固定字段的版本化问答 | `/api/v1/query` | 和 `/api/query` 并列，不是替代治理 |
| 谁能搜哪类资料 | `/api/retrieval/policies*` | 单机演示可以不配 |

`knowledge_base/` 是资料库的另一套模块实现，现网工作台主路径打的是 `/api/delivery/documents`。两套都留在仓库，对接时不要各写各的版本号。

发布资料之后，检索投影要看 `GET /api/delivery/documents-index/status`，必要时 `rebuild`。发布图之后，沿边问答用的 GraphStore 要看是否 `resync`。只看到“发布成功”不够。

## Skill 和模型槽

对外交的是 Skill：`.agents/skills/govern-graphrag-delivery/`。

- 说明书：`SKILL.md`、`references/`、`assets/`
- 完整实现副本：`code/`（解析、治理库、图谱、问答、出表、`/api/delivery`、测试）
- 刷新副本：`python .agents/skills/govern-graphrag-delivery/scripts/pack_code.py`
- 工作台运行时仍从仓库根目录导入同名模块

Skill 被唤起时，**调用方自己填模型槽**：抽关系、写 FMEA 字段、识图缺口、问答组织。不要向客户要 OpenAI / embedding 钥匙。写回走本地 `/api/delivery`。服务器继续管落盘、审核、版本、发布。

不要用 Skill 填：没有批准政策的 S/O/D、RPN；书里没有的情节；打不开的证据号。

## 部署与运行时

| 项 | 位置或约定 |
|---|---|
| 进程 | `python api_server/current_console/server.py` 或 `PowerRAG.exe` |
| 端口 | 默认 `127.0.0.1:8000`，占用时看启动窗口 |
| 应用版本 | `/api/health` 里的 2.1.0 |
| 向量库 / 上传 / 日志 | `%LOCALAPPDATA%\\PowerRAG\\current_console\\` |
| 治理库 | 项目工作区里的 `governance/delivery.sqlite3`（`GovernanceStore`） |
| 运行图库 | 工作台配置的 GraphStore SQLite，和治理库分开 |
| 默认分类 / 集合 | 领域 `gas_turbine`；快路径集合 `power_equipment` |
| 默认操作人 | `local-user` |
| 出表模板 | `configs/fmea/gas_turbine_minimum_v1.yaml`（1.1.0，已批准）。电动机模板未单独验收 |
| DOCX 精确页 | 本机 Office 或 LibreOffice；没有就只能看渲染页或原图 |
| 识图 | 本机引擎；没有且页图已在上下文，由调用方认字再 `ocr-result` |
| Electron | 仓里保留，现网不启动 |
| 客户包 | `desktop_launcher/dist/PowerRAG/` 必须带 `_internal` |

本机冒烟（不代替现场资料验收）：

```powershell
python -m pytest tests/unit/test_governed_delivery_workflow.py tests/unit/test_delivery_api.py -q
```

## 共享对象

这些结构在 `core_domain/delivery.py`，接口来回都是它们。

**证据号 `EvidenceLocator`**：`evidence_id`、`document_version_id`、`chunk_id`、`text`、`source_file`，以及可选的 `page`、`block_id`、`table_id`、`image_id`。图上的边和表上的字段最后都要能 `GET /api/delivery/evidence/{id}/open`。

**资料版本状态**：`candidate` → `needs_review` → `published` / `retired`。没有证据、最近一次审核不是批准，不能 `publish`。改正文走 `revise`，出新版本号，旧版可对照。

**审核结论**：`approve` / `confirm` / `reject` / `modify` / `rollback`。只增记录，不改历史行。

**图谱关系 `GraphStatement`**：`subject`、`predicate`、`object`（库里列名 `object_name`）、`subject_type`、`object_type`、`evidence_ids`（至少一条）、可选 `confidence`、`knowledge_type`（默认 FACT）。类型和关系必须在已批准 Schema 里。

**故障分析表一行 `FMEAItem`**：字段只能是下面七个；每个字段另存 `field_evidence`。未知字段直接拒绝。空着比编造好。

## 治理库表

文件：项目工作区 `governance/delivery.sqlite3`。只记账，不回答问题。

| 表 | 记什么 |
|---|---|
| `document_versions` | 资料版本、状态、哈希、替代谁 |
| `evidence_locators` | 证据号到页、块、原文 |
| `source_assets` | 原文件字节和页数 |
| `ocr_jobs` | 识图任务、失败页、重试次数 |
| `document_review_tasks` | 整页待审 |
| `graph_versions` | 图谱版本、所用资料版本、Schema |
| `graph_statements` | 每一条带证据的关系 |
| `reviews` | 对资料 / 图 / 表的审核 |
| `fmea_tasks` | 出表任务、行 JSON、状态 |
| `fmea_task_events` | 出表状态迁移 |
| `feedback` | 问题指回哪个模块 |
| `feedback_runs` | 是不是真的重跑了上游 |

向量在 Chroma。运行图在 `GraphStore`。三套对不上时，先看索引状态和是否 `resync`，不要只清向量。

## 出表字段和图谱最小链

模板 `gas_turbine_minimum_v1` / 1.1.0：

| 字段 | 中文 | 必填 |
|---|---|---|
| `equipment` | 设备 | 是 |
| `component` | 部件/系统 | 是 |
| `failure_mode` | 故障模式 | 是 |
| `cause` | 原因 | 是 |
| `effect` | 影响 | 是 |
| `detection_method` | 检测方法 | 是 |
| `recommended_action` | 建议措施 | 是 |

每字段必须带证据。`scoring_policy.automatic_s_o_d_scores` 为 false，不写严重度、频度、探测度，不编风险优先数。

图谱最小故障链（关系必须在已批准规则里）：

- `HAS_FAILURE_MODE`：设备/系统/部件 → 故障模式
- `CAUSED_BY`：故障模式 → 原因
- `HAS_EFFECT`：故障模式 → 影响
- `DETECTED_BY`：故障模式 → 检测方法
- `MITIGATED_BY`：故障模式 → 措施

导出 JSON / CSV / DOCX 之后打 `export-verify`，三份行数必须一致。

## HTTP 状态

| 码 | 意思 | 常见原因 |
|---|---|---|
| 200 / 201 / 202 | 成功 / 已创建 / 已接受后台任务 | 202 时拿任务号轮询 |
| 404 | 找不到 | 版本号、任务号、项目号写错 |
| 409 | 状态不允许或版本冲突 | 没批准就发布；`expected_version` 对不上 |
| 413 | 太大 | 上传或整包超限 |
| 415 | 类型不支持 | 文件类型不在解析器里 |
| 422 | 参数不合法 | 缺字段、枚举不对、缺证据号 |
| 500 | 程序失败 | 先看日志，不当成治理拒绝 |
| 503 | 模型或依赖不可用 | 没配提供方还打了 `/extract`、全局问答 |

治理拒绝（缺证据、未发布、类型不在规则里）应是 4xx 和返回体里的错误码，不要改数据假装成功。
"""


def inventory_section() -> str:
    return r"""
## 有内容就不能直接删

程序里只要已经写下东西，就不能当没发生过。正式资料、图、表、审核、反馈、验收材料，都不走“直接从库里抹掉”。能退回、能作废、能撤回、能被新版替换，但旧版、意见、时间、操作人要留在治理库或审计表里。

这份说明同样遵守这一条：仓库里有内容的程序面，不管现网导航还在不在用，都记在下面。空缓存、临时扫描目录除外。

不能直接抹掉的，包括：

- 已发布资料版本。只能回滚到更早的正式版，或再出新稿。旧正式版还在，能对照。
- 已发布图谱。只能回滚或再发新版。边上的证据号还要能打开。
- 已发布故障分析表。v1 线用撤回、替换；工作台线用新任务和反馈。发布体和生命周期事件留下。
- 审核结论、字段修改、反馈、整改跑次。只增不改历史。
- 验收材料。改写必须带当前哈希，旧哈希进审计日志。
- 项目整包。导出带清单和哈希；恢复失败不能装成成功。
- 图谱规则、出表模板。状态是草案 / 已批准 / 已退役，退役不是从磁盘抹掉。
- 检索策略。有历史、能退回上一版。
- 对话记忆。可以清会话，但那是会话自己的删除接口，不是治理正式版。
- 仓库源码和历史成果。`archive/`、`electron/`、`RAG交付/`、隐藏页、旧前端，有内容就留着，现网不用也不删仓。

工作台上传文件、检索集合可以删，那是快路径上的落盘和向量，不是治理正式版。删上传会写操作日志。删集合是真的拿掉向量，打之前先导出。

## 程序目录清单

现网跑起来必用的，和仓里有内容但现网不挂导航的，都列在这里。处置列的是“能不能从仓库删”，不是“现网开不开”。

| 目录或入口 | 有什么 | 现网 | 处置 |
|---|---|---|---|
| `api_server/current_console/` | FastAPI 现网，218 条接口 | 用 | 主入口，不能删 |
| `api_server/current_console/legacy/` | 旧控制台、旧向量封装 | 不用 | 有代码，归档参考，不删 |
| `frontend_app/current_console/` | 工作台 HTML/JS/CSS | 用 | 主界面，不能删 |
| `frontend_app/current_console/fmea/` 与 `fmea.html` | 出表治理 v1 子工作台 | 用，另开一页 | 有完整页面，不能删 |
| `desktop_launcher/` | Windows 可执行文件打包 | 客户用 | 不能删。`dist/` 不进 git，给客户另附 |
| `electron/` | 旧桌面壳 | 交付不用 | 有主进程和预加载，仓里保留，不删、不启动 |
| `RAG交付/` | 历史快照，接口是子集 | 不用 | 有前后端，不删、不当现网 |
| `data_pipeline/` | 解析、识图、公开书目、数据集 | 被接口调用 | 不能删 |
| `knowledge_base/` | M3 规范库：不可变修订、快照、作废、回滚、带校验备份 | 模块在 | 不能删。和 `/api/delivery/documents` 是同一段能力的另一套实现 |
| `storage_layer/` | 治理库、向量、图库、项目工作区、对话记忆 | 用 | 不能删 |
| `kg_pipeline/` | 抽关系、社区、受控抽取 | 用 | 不能删 |
| `rag_orchestrator/` | 问答编排、沿图、出表、整改 | 用 | 不能删 |
| `retrieval_engine/` | 稠密 / 稀疏 / 图 / 混合检索 | 用 | 不能删 |
| `core_domain/` | 资料、块、证据、出表等共享结构 | 用 | 不能删 |
| `fmea_application/`、`fmea_infrastructure/` | 出表组装、Office 包 | 用 | 不能删 |
| `workflow_runtime/` | M6 单机编排：DAG、重试、取消、检查点、运行报告 | 模块在 | 不能删。不替代解析到出表的专业实现 |
| `model_adapters/` | 模型客户端 | 按配置 | 不能删 |
| `configs/` | 出表模板、书目过滤 | 用 | `gas_turbine_minimum_v1.yaml` 现网用。`electric_motor_minimum_v1.yaml` 是扩展，未单独验收，文件留下 |
| `templates/`、`domain_packs/` | 出表和领域模板 | 有内容 | 不删 |
| `structured_generation_*`、`structured_output_*` | 结构化生成 / 输出 | 有代码和例子 | 不删 |
| `evaluation/` | 门禁、金标、评测报告 | 验收用 | 不删 |
| `tests/` | 单测、集成、浏览器测 | 质量用 | 不删 |
| `scripts/` | 启动、验收、演练脚本 | 用 | 不删 |
| `docs/` | PRD、接口契约、阶段成果 | 有内容 | 不删。`docs/project_deliverables/` 是早期到现在的材料包 |
| `observability/` | 运行记录说明 | 有内容 | 不删 |
| `examples/` | 出表和结构化生成例子 | 有内容 | 不删 |
| `skills/`、`.agents/skills/` | 代理技能和代码副本 | 有内容 | 不删。改模块后用 `scripts/pack_code.py` 刷新副本，不要只改一份 |
| `archive/` | 郭老师早期实验、旧子仓快照 | 不用 | 只读参考，不删、不往里堆新功能 |
| `mooncake-material-studio/`、`mooncake-redesign-references/` | 原型和视觉参考 | 不是产品线 | 有内容，不删 |
| `design_concepts/`、`html_ppt/`、`rag_history_papers/` | 设计稿、页、论文材料 | 不是现网 | 有内容，不删 |
| `experiments/`、`external_repos/`、`integrations/`、`tools/` | 实验、外部仓、集成、工具 | 按需 | 有内容就留着 |
| `build/` | 当前验收包输出 | 生成物 | 可重建，但已生成的验收包不要随手抹 |
| `storage_layer/runtime/` 与 `%LOCALAPPDATA%\PowerRAG\current_console\` | 运行时向量、上传、日志 | 运行数据 | 不是源码。清库等于丢掉现场资料，先导出 |

下面这些**可以**不写进产品说明的正文，因为没有要保留的程序内容：`.pytest_cache/`、`tmp_route_scan/`、`tmp_prd_extract/` 这类临时扫描。

## 界面全部页面

`frontend_app/current_console/index.html` 里挂着的页面，包括现网导航不展示的，都记在这里。HTML 还在，模块还在，不能当废文件删。

| 页面 id | 文件 | 现网导航 | 做什么 |
|---|---|---|---|
| `page-data` | `modules/pages/data-page.js` | M1 资料接入 | 上传、解析、写入检索库 |
| `page-kg_data` | `modules/pages/kg-data-page.js` | M2 知识组织 | 构图、社区、导入导出运行图 |
| `page-kg_search` | `modules/pages/kg-search-page.js` | M3 图谱问答 | 提问、多轮 |
| `page-delivery` | `modules/pages/delivery-page.js` | M4 可信交付 | 项目、审核、发布、出表 |
| `page-acceptance` | `modules/pages/acceptance-page.js` | M5 验收 | 门禁和验收包 |
| `page-overview` | `modules/pages/overview-page.js` | 抽屉 · 总览 | 运行状态 |
| `page-admin` | `modules/pages/admin-page.js` | 抽屉 · 设置 | 集合、策略、身份、日志 |
| `page-search` | `modules/pages/search-page.js` | **不挂导航** | 旧语义检索页，代码还在 |
| `page-kg` | `modules/pages/kg-page.js` | **不挂导航** | 旧图谱页，代码还在 |

另开一页，不在五页导航里，但程序完整：

| 入口 | 文件 | 做什么 |
|---|---|---|
| `/fmea.html` | `fmea/app.js` 及 `fmea/views/*.js` | 出表治理 v1：分析、证据、审核、风险、传播、模板、导出、发布 |

`fmea/views/` 现有：`analysis.js`、`evidence.js`、`review.js`、`risk.js`、`propagation.js`、`templates.js`、`exports.js`、`governance.js`。每一页都打 `/api/v1/fmea/*`，不能只记工作台 `/api/delivery/fmea`。

共用脚本也留下：`modules/console-app.js`、`delivery-api.js`、`delivery-state.js`、`delivery-components.js`、`page-registry.js`。样式 `styles/console.css`、`styles/industrial-ops.css`。本机库 `libs/`（PDF、DOCX、Tesseract、D3 等）是界面能力，不删。

`RAG交付/frontend_app/index.html` 是历史界面副本，不接现网 218 条，文件留下。

## 作废撤回和删除怎么留痕

正式对象不提供“从治理库物理抹掉”的接口。能做的是退回、作废、撤回、替换，并且记账。

| 动作 | 接口 | 留下什么 | 不能做什么 |
|---|---|---|---|
| 资料退回旧正式版 | `POST /api/delivery/documents/{document_id}/rollback` | 新旧版本都在，审计可查 | 不能把已发布版当成从没存在过 |
| 图谱退回旧正式版 | `POST /api/delivery/graphs/rollback` | 旧图版本仍可对照 | 不能只删边上的证据号 |
| 检索策略退回 | `POST /api/retrieval/policies/rollback` | 历史仍在 `/history` | 不能无记录改正式策略 |
| 批准撤回 | `POST /api/v1/fmea/approvals/{id}/withdrawals` | 审批事件 | 不能悄悄改已批结论 |
| 发布撤回 | `POST /api/v1/fmea/publications/{id}/withdrawals` | 生命周期事件 | 不能当这份发布没出过 |
| 新发布替换旧发布 | `POST /api/v1/fmea/publications/{id}/supersessions` | 新旧发布都在 | 不能覆盖写掉旧快照 |
| 规则或模板退役 | 项目里状态改为 `retired` | 记录仍在，不能再批准使用 | 不能从项目表抹行 |
| 出表反馈 | `POST /api/delivery/fmea/tasks/{id}/feedback` | 反馈和整改跑次 | 不能只改表上的字不记账 |
| 改验收材料 | `PUT /api/delivery/acceptance/artifacts/{key}` | 旧哈希、新哈希进 `acceptance_audit.jsonl` | 不带当前哈希不能覆盖 |

下面这些是**真删除**，只作用于非治理正式版，仍应先看日志或先导出：

| 动作 | 接口 | 说明 |
|---|---|---|
| 删一份上传 | `DELETE /api/uploads/{filename}` | 删工作台落盘，写操作日志。不影响已发布治理版本 |
| 批量删上传 | `POST /api/uploads/delete` | 同上 |
| 删检索集合 | `DELETE /api/collections/{name}` | 真的拿掉向量。打之前先 `/api/export/{name}` |
| 清空运行图库 | `POST /api/graphrag/reset` | 删运行投影文件。治理库里的图谱版本还在 |
| 清对话消息 | `DELETE /api/memory/sessions/{id}/messages` | 只清会话 |
| 删对话 | `DELETE /api/memory/sessions/{id}` | 只清会话 |
| 注销登录会话 | `DELETE /api/retrieval/policies/identity-provider/sessions/{id}` | 只关登录，不动资料 |

项目审计：`GET /api/delivery/projects/{project_id}/audit`。任务评论、心跳、取消、重试都进任务中心，不覆盖旧行。

"""


def build() -> str:
    routes = catalog.load_routes()
    openapi = load_openapi()
    grouped_counts = {title: 0 for title, _ in catalog.FAMILIES}
    for method, path, _ in routes:
        grouped_counts[catalog.family_of(method, path)] = grouped_counts.get(catalog.family_of(method, path), 0) + 1
    counts = "\n".join(f"- {title}：{grouped_counts[title]} 条" for title, _ in catalog.FAMILIES)
    chunks = [
        front_matter(routes),
        inventory_section(),
        "## 现网全部接口\n",
        f"合计 {len(routes)} 条。\n",
        counts + "\n",
    ]
    grouped: dict[str, list[tuple[str, str, str]]] = {title: [] for title, _ in catalog.FAMILIES}
    grouped["其他"] = []
    for item in routes:
        grouped[catalog.family_of(item[0], item[1])].append(item)
    for title, _ in catalog.FAMILIES:
        items = grouped[title]
        chunks.append(f"### {title}\n")
        chunks.append(FAMILY_INTRO[title] + "\n")
        chunks.append(f"本族 {len(items)} 条。\n")
        for method, path, name in items:
            chunks.append(render_endpoint(method, path, name, openapi))
    chunks.append("## 受控失败\n")
    chunks.append(
        "这些是治理结果，不是要绕开的程序错。\n\n"
        "- 扫描件缺字、缺页码、识图失败：停在待审，不能发布正式资料。\n"
        "- 没有批准：不能发布资料，也不能构图。\n"
        "- 未发布资料：不能作为构图来源。\n"
        "- 类型或关系不在已批准规则里：不能发布图。\n"
        "- 证据缺失，或证据不在所选版本：不能发布图。\n"
        "- 未发布图：不能出表。\n"
        "- 字段对不上或互相打架：保持空，挂上证据号，不编严重度、频度、探测度。\n"
        "- 没有批准的评分政策：不写风险优先数。\n"
        "- 未发布的表：不能当正式导出。\n"
        "- 只建反馈记录：不等于已经重跑解析、重建索引或重发图。\n"
        "- 验收门禁没齐：验收包可以生成，总状态不能写成通过。\n"
        "- 同一账号签两个角色：端到端验收不认。\n"
        "- 已发布资料、图、表：不能从治理库直接抹掉。只允许回滚、作废、撤回、替换，并且记账。\n"
        "- 隐藏页、旧桌面壳、历史快照、归档实验：仓里有内容就保留，不从仓库直接删。\n"
    )
    chunks.append("## 术语\n")
    chunks.append(
        "- **FMEA**：故障模式与影响分析。把设备、故障、原因、措施做成一张表。\n"
        "- **OCR**：光学字符识别，也就是识图取字。\n"
        "- **证据号**：能打开到资料版本、页、块的稳定编号。\n"
        "- **正式版 / 已发布**：审核通过后才允许下游使用的版本。\n"
        "- **治理库**：记审核和版本的账本，不是向量库。\n"
        "- **向量库**：按切块做相似检索的 Chroma。\n"
        "- **图库**：点和边的 SQLite，给沿边问答用。\n"
        "- **Schema**：允许出现的实体类型和关系类型。\n"
        "- **S / O / D**：严重度、频度、探测度。没有批准政策就不写。\n"
        "- **RPN**：风险优先数，一般由上面三项算出来。这里禁止空算。\n"
        "- **GraphRAG**：先沿图上的边取证，再组织回答；取不够就退回普通检索。\n"
        "- **OpenAPI**：机器可读的接口清单，现网在 `/openapi.json`。\n"
        "- **Skill**：`.agents/skills/govern-graphrag-delivery`，说明书加 `code/` 里的实现副本。\n"
    )
    return "\n".join(chunks).replace("{{", "{").replace("}}", "}")


def main() -> None:
    if not OPENAPI.is_file():
        raise SystemExit(f"missing {OPENAPI}，先跑 python tmp_dump_openapi.py")
    text = build()
    for dest in DESTS:
        dest.write_text(text, encoding="utf-8")
        print(dest, dest.stat().st_size, "bytes", text.count("\n"), "lines")


if __name__ == "__main__":
    main()
