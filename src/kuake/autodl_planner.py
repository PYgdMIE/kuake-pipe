"""AutoDL instance-create payload planner.

构造 POST /api/v1/order/instance/create/payg 的 body,**只输出不发送**。
用户可以看清所有字段(GPU 数 / 镜像 / 数据盘扩容 / 系统盘扩容 / 优惠券),
确认后再决定要不要真的下单。

v0.4 起,clone 模式可以从已有实例的 detail 中提取配置,生成"开同款"payload。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from kuake.autodl_api import MachineMatch

# 默认公共镜像 (PyTorch / Conda) — 与 AutoDL 控制台同
DEFAULT_IMAGE_NVIDIA = (
    "hub.kce.ksyun.com/autodl-image/torch:"
    "cuda12.8-cudnn-devel-ubuntu22.04-py312-torch2.8.0"
)
DEFAULT_IMAGE_CPU = (
    "hub.kce.ksyun.com/autodl-image/miniconda3:py311-ubuntu22.04"
)


@dataclass
class InstancePlan:
    """完整的 create 请求 plan,可序列化也可打印。"""
    machine_id: str
    machine_alias: str
    region_name: str
    gpu_name: str
    chip_corp: str
    req_gpu_amount: int = 1
    image: str = ""
    private_image_uuid: str = ""
    reproduction_uuid: str = ""
    expand_data_disk: int = 0       # 单位 GB,0 表示不扩容
    system_disk_change_size: int = 0  # GB 扩容(超过默认 30 G 的部分)
    duration: int = 1
    num: int = 1
    coupon_id_list: list[str] = field(default_factory=list)
    # 显示/对比用,不进 payload
    payg_price_yuan_per_hour: float = 0.0
    source_instance_uuid: str = ""   # clone 模式记一下来源
    notes: list[str] = field(default_factory=list)

    def to_payload(self) -> dict:
        """构造真实 POST body (但调用方不直接发送, 留给用户最后确认)。

        Schema 来自 2026-05 抓的 AutoDL Web UI 真实流量:
        - expand_data_disk 单位是字节,不是 GB (plan 里存的是 GB)
        - duration/num/coupon_id_list 拆在顶层 price_info,不在 instance_info
        - system_disk_change_size 只在非零时发送
        """
        expand_bytes = self.expand_data_disk * 1024 ** 3
        instance_info: dict = {
            "machine_id": self.machine_id,
            "charge_type": "payg",
            "req_gpu_amount": self.req_gpu_amount,
            "image": self.image,
            "private_image_uuid": self.private_image_uuid,
            "reproduction_uuid": self.reproduction_uuid,
            "cg_application_uuid": "",
            "cg_application_info": {
                "app_name": "",
                "current_version_id": 0,
                "current_version": "",
                "image_id": 0,
            },
            "instance_name": "",
            "expand_data_disk": expand_bytes,
            "reproduction_id": 0,
        }
        if self.system_disk_change_size:
            instance_info["system_disk_change_size"] = self.system_disk_change_size * 1024 ** 3
        return {
            "instance_info": instance_info,
            "price_info": {
                "coupon_id_list": self.coupon_id_list,
                "machine_id": self.machine_id,
                "charge_type": "payg",
                "duration": self.duration,
                "num": self.num,
                "expand_data_disk": expand_bytes,
            },
        }

    def estimated_hour_cost(self) -> float:
        """每小时花费(元),不含扩容费用(扩容费另算)。"""
        return self.payg_price_yuan_per_hour * self.req_gpu_amount * self.num


def plan_from_match(
    match: MachineMatch,
    *,
    gpu_count: int = 1,
    image: str | None = None,
    private_image_uuid: str = "",
    expand_data_disk_gb: int = 0,
    system_disk_change_size_gb: int = 0,
    duration: int = 1,
) -> InstancePlan:
    """从一台市场机器构造 plan(default 公共镜像 + 不扩容)。"""
    chip_corp = (match.chip_corp or "nvidia").lower()
    chosen_image = image
    if chosen_image is None:
        chosen_image = DEFAULT_IMAGE_CPU if chip_corp == "cpu" else DEFAULT_IMAGE_NVIDIA

    return InstancePlan(
        machine_id=match.machine_id,
        machine_alias=match.machine_alias,
        region_name=match.region_name,
        gpu_name=match.gpu_name,
        chip_corp=chip_corp,
        req_gpu_amount=gpu_count,
        image=chosen_image,
        private_image_uuid=private_image_uuid,
        expand_data_disk=expand_data_disk_gb,
        system_disk_change_size=system_disk_change_size_gb,
        duration=duration,
        payg_price_yuan_per_hour=match.payg_price / 1000 if match.payg_price else 0.0,
    )


def plan_clone_from_instance(
    source_instance: dict,
    target_match: MachineMatch,
    *,
    gpu_count: int | None = None,
    expand_data_disk_gb: int | None = None,
    system_disk_change_size_gb: int | None = None,
) -> InstancePlan:
    """从已有实例的 detail dict 克隆配置,目标机器替换为 target_match。

    用法:已有实例 instance_uuid 打不开了, 找一台同 GPU 的新机器 target_match,
    把镜像/扩容设置复制过来开同款。
    """
    chip_corp = ""
    snapshot_gpu = source_instance.get("snapshot_gpu_alias_name") or ""
    if "cpu" in snapshot_gpu.lower() or source_instance.get("start_mode") == "cpu":
        chip_corp = "cpu"
    else:
        chip_corp = "nvidia"

    image = source_instance.get("image", "")
    private_image_uuid = source_instance.get("private_image_uuid", "")
    if not image and not private_image_uuid:
        image = DEFAULT_IMAGE_CPU if chip_corp == "cpu" else DEFAULT_IMAGE_NVIDIA

    src_gpu_count = int(source_instance.get("req_gpu_amount", 1))
    chosen_gpu_count = gpu_count if gpu_count is not None else src_gpu_count

    # 数据盘 / 系统盘扩容 — 如果源实例信息含,用它;否则默认 0
    if expand_data_disk_gb is None:
        # disk_expand_available 是是否曾扩过,具体扩量没直接给。保守用 0,后续可让用户传
        expand_data_disk_gb = 0
    if system_disk_change_size_gb is None:
        system_disk_change_size_gb = 0

    plan = InstancePlan(
        machine_id=target_match.machine_id,
        machine_alias=target_match.machine_alias,
        region_name=target_match.region_name,
        gpu_name=target_match.gpu_name,
        chip_corp=chip_corp,
        req_gpu_amount=chosen_gpu_count,
        image=image,
        private_image_uuid=private_image_uuid,
        reproduction_uuid=source_instance.get("reproduction_uuid", ""),
        expand_data_disk=expand_data_disk_gb,
        system_disk_change_size=system_disk_change_size_gb,
        duration=1,
        payg_price_yuan_per_hour=target_match.payg_price / 1000
            if target_match.payg_price else 0.0,
        source_instance_uuid=source_instance.get("uuid", ""),
        notes=[
            f"从 instance {source_instance.get('uuid','?')[:12]}.. ({source_instance.get('machine_alias','?')}) 克隆配置",
            f"原 GPU: {source_instance.get('snapshot_gpu_alias_name','?')} × {src_gpu_count}",
            f"原状态: {source_instance.get('status','?')}",
        ],
    )
    return plan


def format_plan(plan: InstancePlan) -> str:
    """美化打印 plan,供用户最后人工确认。"""
    lines = []
    lines.append("┌─ AutoDL 实例创建 PLAN (dry-run, 不发请求) ───────────────")
    lines.append(f"│ 区域 / 机器  : {plan.region_name} / {plan.machine_alias} "
                 f"(id={plan.machine_id})")
    lines.append(f"│ GPU         : {plan.gpu_name} × {plan.req_gpu_amount}")
    lines.append(f"│ 芯片        : {plan.chip_corp}")
    if plan.private_image_uuid:
        lines.append(f"│ 镜像        : [私有] uuid={plan.private_image_uuid}")
    elif plan.reproduction_uuid:
        lines.append(f"│ 镜像        : [社区复现] uuid={plan.reproduction_uuid}")
    else:
        lines.append(f"│ 镜像        : [公共] {plan.image}")
    lines.append(f"│ 数据盘扩容  : +{plan.expand_data_disk} GB (默认 50G;0=不扩)")
    lines.append(f"│ 系统盘扩容  : +{plan.system_disk_change_size} GB (默认 30G;0=不扩)")
    lines.append(f"│ 数量        : {plan.num} 台 × {plan.duration} 单位时长")
    lines.append(f"│ 单价        : ¥{plan.payg_price_yuan_per_hour:.2f}/小时")
    lines.append(f"│ 估算时费    : ¥{plan.estimated_hour_cost():.2f}/小时")
    if plan.coupon_id_list:
        lines.append(f"│ 优惠券      : {plan.coupon_id_list}")
    if plan.source_instance_uuid:
        lines.append(f"│ 克隆来源    : {plan.source_instance_uuid}")
    if plan.notes:
        for note in plan.notes:
            lines.append(f"│   * {note}")
    lines.append("├─ 完整 POST body (供人工审计) ─────────────────────────")
    payload_json = json.dumps(plan.to_payload(), ensure_ascii=False, indent=2)
    for ln in payload_json.splitlines():
        lines.append(f"│ {ln}")
    lines.append("└────────────────────────────────────────────────────────")
    lines.append("⚠ 不会真下单 — 此 PLAN 仅供你 review。")
    lines.append("  确认后想真创建: kuake confirm-create --plan-file <plan.json>")
    return "\n".join(lines)


def save_plan(plan: InstancePlan, path: str) -> None:
    """落盘成 JSON 供 kuake confirm-create 复读。"""
    payload = {
        "plan": {
            "machine_id": plan.machine_id,
            "machine_alias": plan.machine_alias,
            "region_name": plan.region_name,
            "gpu_name": plan.gpu_name,
            "chip_corp": plan.chip_corp,
            "req_gpu_amount": plan.req_gpu_amount,
            "image": plan.image,
            "private_image_uuid": plan.private_image_uuid,
            "reproduction_uuid": plan.reproduction_uuid,
            "expand_data_disk": plan.expand_data_disk,
            "system_disk_change_size": plan.system_disk_change_size,
            "duration": plan.duration,
            "num": plan.num,
            "coupon_id_list": plan.coupon_id_list,
            "payg_price_yuan_per_hour": plan.payg_price_yuan_per_hour,
            "source_instance_uuid": plan.source_instance_uuid,
        },
        "payload": plan.to_payload(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
