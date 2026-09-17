"""Deterministic mission orchestration above the Josie Supervisor."""

from .campaign_bridge import (
    BridgeAuthorityError,
    BridgeError,
    CampaignBridge,
    MissionNotFoundError,
    MissionState,
    MissionValidationError,
    plan_to_campaign_spec,
    validate_mission_plan,
)
from .dispatcher import DispatchError, MissionManager
from .ingress import continue_mission, mission_status, submit_mission
from .models import PlanValidationError

__all__ = [
    "DispatchError",
    "MissionManager",
    "PlanValidationError",
    "CampaignBridge",
    "MissionState",
    "BridgeError",
    "MissionValidationError",
    "MissionNotFoundError",
    "BridgeAuthorityError",
    "validate_mission_plan",
    "plan_to_campaign_spec",
    "continue_mission",
    "mission_status",
    "submit_mission",
]
__version__ = "0.1.1"

