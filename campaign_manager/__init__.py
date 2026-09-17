from __future__ import annotations

from .adapter import FakeSupervisorAdapter, RealSupervisorAdapter, SupervisorAdapter, SupervisorResult
from .constants import CampaignStatus, EventType, JobState
from .errors import (
    CampaignAlreadyRunningError,
    CampaignManagerError,
    CampaignNotFoundError,
    CycleDetectedError,
    DoubleClaimError,
    InvalidStateTransitionError,
    JobNotFoundError,
    LeaseError,
    StaleLeaseError,
    SupervisorIntegrationError,
    UncertainExecutionError,
    ValidationError,
)
from .manager import CampaignManager
from .models import AttemptRecord, CampaignRecord, EventRecord, JobRecord

__version__ = "0.1.1"

__all__ = [
    "CampaignManager",
    "CampaignStatus",
    "JobState",
    "EventType",
    "CampaignManagerError",
    "ValidationError",
    "CycleDetectedError",
    "InvalidStateTransitionError",
    "JobNotFoundError",
    "CampaignNotFoundError",
    "LeaseError",
    "StaleLeaseError",
    "DoubleClaimError",
    "CampaignAlreadyRunningError",
    "SupervisorIntegrationError",
    "UncertainExecutionError",
    "SupervisorAdapter",
    "RealSupervisorAdapter",
    "FakeSupervisorAdapter",
    "SupervisorResult",
    "AttemptRecord",
    "CampaignRecord",
    "JobRecord",
    "EventRecord",
]
