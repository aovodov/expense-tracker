"""Месячный бюджет: превышен ли он и сколько денег осталось."""

from .money import format_amount


def is_over_budget(spent: float, budget: float) -> bool:
    """Бюджет превышен только тогда, когда расходы строго больше бюджета."""
    return spent > budget


def remaining(spent: float, budget: float) -> float:
    """Остаток бюджета. Отрицательное число означает перерасход."""
    return budget - spent


def budget_report(spent: float, budget: float) -> str:
    """Короткое сообщение о состоянии бюджета."""
    if is_over_budget(spent, budget):
        return f"Бюджет превышен на {format_amount(-remaining(spent, budget))}"
    return f"Осталось {format_amount(remaining(spent, budget))}"
