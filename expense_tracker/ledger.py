"""Реестр расходов: добавление, отбор за месяц и по категории, суммы."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from .money import format_amount, parse_amount


@dataclass(frozen=True)
class Expense:
    """Один расход: когда, на что и сколько потрачено."""

    date: date
    category: str
    amount: float
    comment: str = ""


def new_expense(date_text: str, category: str, amount_text: str, comment: str = "") -> Expense:
    """Создаёт расход из строк, которые ввёл пользователь.

    Бросает ``ValueError`` с понятным сообщением, если дата или сумма неверные.
    """
    try:
        expense_date = date.fromisoformat(date_text.strip())
    except ValueError:
        message = f"Дата должна быть в формате ГГГГ-ММ-ДД, получено «{date_text}»"
        raise ValueError(message) from None
    amount = parse_amount(amount_text)
    if amount <= 0:
        raise ValueError(f"Сумма должна быть больше нуля, получено «{amount_text}»")
    return Expense(expense_date, category.strip().lower(), amount, comment.strip())


class Ledger:
    """Список расходов и отборы по нему."""

    def __init__(self, expenses: Iterable[Expense] = ()) -> None:
        self._expenses = list(expenses)

    def add(self, expense: Expense) -> None:
        """Добавляет расход в конец списка."""
        self._expenses.append(expense)

    @property
    def expenses(self) -> list[Expense]:
        """Все расходы в порядке добавления."""
        return list(self._expenses)

    def in_month(self, year: int, month: int) -> list[Expense]:
        """Расходы указанного месяца, включая его первый и последний день."""
        return [
            expense
            for expense in self._expenses
            if (expense.date.year, expense.date.month) == (year, month)
        ]

    def in_category(self, category: str) -> list[Expense]:
        """Расходы одной категории. Регистр букв не важен."""
        wanted = category.strip().lower()
        return [expense for expense in self._expenses if expense.category == wanted]


def total(expenses: Iterable[Expense]) -> float:
    """Общая сумма расходов."""
    return sum(expense.amount for expense in expenses)


def totals_by_category(expenses: Iterable[Expense]) -> dict[str, float]:
    """Сумма расходов по каждой категории."""
    result: dict[str, float] = {}
    for expense in expenses:
        result[expense.category] = result.get(expense.category, 0) + expense.amount
    return result


def summary(expenses: Iterable[Expense], title: str) -> str:
    """Текстовый отчёт: сумма по каждой категории и общая сумма."""
    lines = [title]
    for category, amount in sorted(totals_by_category(expenses).items()):
        lines.append(f"  {category}: {format_amount(amount)}")
    lines.append(f"  Всего: {format_amount(total(expenses))}")
    return "\n".join(lines)
