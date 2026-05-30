"""Pre-trade risk gate.

Structurally placed between decision and execution: the strategy *proposes* an
Order, the gate *disposes*. Nothing reaches a live executor without passing
here. This is the difference between a strategy bug (costs you an edge) and a
plumbing bug (costs you the account).

The gate is pure and synchronous — given an order plus the current world
(positions, account balance), it returns approve/reject with a reason. Easy to
unit-test, impossible to bypass if executors are wired to call it first.
"""

from __future__ import annotations

from dataclasses import dataclass

from kalshi_agent.types import Order, Position


@dataclass(frozen=True)
class RiskLimits:
    max_contracts_per_order: int = 50
    max_position_per_market: int = 200
    max_order_notional_cents: int = 50_00  # $50
    kill_switch: bool = False  # flip to halt all trading instantly


@dataclass(frozen=True)
class RiskDecision:
    approved: bool
    reason: str

    def __bool__(self) -> bool:
        return self.approved


class RiskGate:
    def __init__(self, limits: RiskLimits):
        self.limits = limits

    def check(
        self,
        order: Order,
        *,
        position: Position | None,
        balance_cents: int,
    ) -> RiskDecision:
        L = self.limits

        if L.kill_switch:
            return RiskDecision(False, "kill switch engaged")

        if order.quantity <= 0:
            return RiskDecision(False, "non-positive quantity")

        if order.quantity > L.max_contracts_per_order:
            return RiskDecision(
                False,
                f"quantity {order.quantity} exceeds per-order cap {L.max_contracts_per_order}",
            )

        notional = order.notional_cents()
        if notional > L.max_order_notional_cents:
            return RiskDecision(
                False,
                f"notional {notional}c exceeds cap {L.max_order_notional_cents}c",
            )

        if notional > balance_cents:
            return RiskDecision(
                False, f"notional {notional}c exceeds balance {balance_cents}c"
            )

        held = position.quantity if position else 0
        if held + order.quantity > L.max_position_per_market:
            return RiskDecision(
                False,
                f"position {held}+{order.quantity} exceeds cap {L.max_position_per_market}",
            )

        return RiskDecision(True, "ok")
