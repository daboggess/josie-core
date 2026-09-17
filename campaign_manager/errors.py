from __future__ import annotations


class CampaignManagerError(Exception):
    """Base exception for Campaign Manager."""
    pass


class ValidationError(CampaignManagerError):
    """Raised when campaign specification, job payload, or schema is invalid."""
    pass


class CycleDetectedError(ValidationError):
    """Raised when a dependency cycle is detected among campaign jobs."""
    pass


class InvalidStateTransitionError(CampaignManagerError):
    """Raised when an illegal state transition is attempted on a job or campaign."""
    pass


class JobNotFoundError(CampaignManagerError):
    """Raised when a requested job does not exist in the database."""
    pass


class CampaignNotFoundError(CampaignManagerError):
    """Raised when a requested campaign does not exist in the database."""
    pass


class LeaseError(CampaignManagerError):
    """Raised when lease claiming or renewal fails."""
    pass


class DoubleClaimError(LeaseError):
    """Raised when a job is already claimed or running under an active lease."""
    pass


class CampaignAlreadyRunningError(CampaignManagerError):
    """Raised when attempting to execute a campaign already leased to another runner."""
    pass


class StaleLeaseError(LeaseError):
    """Raised when an operation encounters an expired or invalid lease."""
    pass


class SupervisorIntegrationError(CampaignManagerError):
    """Raised when the Supervisor execution boundary fails unexpectedly."""
    pass


class UncertainExecutionError(CampaignManagerError):
    """Raised when execution outcome cannot be verified from machine evidence."""
    pass
