"""Research-only opportunity and hardware tracking with zero execution authority."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .storage import LocalStore


def money_to_cents(value: str, *, label: str) -> int:
    try:
        amount = Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError(f"{label} must be a number") from exc
    if not amount.is_finite() or amount < 0 or amount > Decimal("1000000000"):
        raise ValueError(f"{label} is outside the permitted research range")
    return int(amount * 100)


def hours_to_milli(value: str) -> int:
    try:
        hours = Decimal(value).quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise ValueError("Estimated hours must be a number") from exc
    if not hours.is_finite() or hours <= 0 or hours > Decimal("1000000"):
        raise ValueError("Estimated hours are outside the permitted research range")
    return int(hours * 1_000)


def record_opportunity(
    *,
    store: LocalStore,
    title: str,
    source: str,
    estimated_revenue: str,
    estimated_cost: str,
    estimated_hours: str,
    risk: str,
    notes: str,
) -> dict[str, object]:
    return store.record_economic_opportunity(
        title=title,
        source=source,
        estimated_revenue_cents=money_to_cents(
            estimated_revenue, label="Estimated revenue"
        ),
        estimated_cost_cents=money_to_cents(estimated_cost, label="Estimated cost"),
        estimated_hours_milli=hours_to_milli(estimated_hours),
        risk=risk,
        notes=notes,
    )


def record_upgrade_target(
    *,
    store: LocalStore,
    component: str,
    target_price: str,
    expected_capability: str,
    compatibility: str,
    notes: str,
) -> dict[str, object]:
    return store.record_hardware_target(
        component=component,
        target_price_cents=money_to_cents(target_price, label="Target price"),
        expected_capability=expected_capability,
        compatibility_status=compatibility,
        notes=notes,
    )
