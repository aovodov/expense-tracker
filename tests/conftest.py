"""Общие приспособления для тестов."""

from datetime import date

import allure
import pytest

from expense_tracker.ledger import Expense

EPIC = "Учёт расходов"


def pytest_collection_modifyitems(items):
    """Относит каждый тест к эпику, чтобы в отчёте Allure TestOps тесты были сгруппированы."""
    for item in items:
        item.add_marker(allure.epic(EPIC))


@pytest.fixture
def expenses() -> list[Expense]:
    """Расходы за ноябрь и декабрь 2026 года."""
    return [
        Expense(date(2026, 11, 1), "еда", 350.5, "Обед"),
        Expense(date(2026, 11, 15), "транспорт", 60.0, "Метро"),
        Expense(date(2026, 11, 30), "еда", 1200.0, "Продукты"),
        Expense(date(2026, 12, 2), "еда", 410.99, "Продукты"),
    ]
