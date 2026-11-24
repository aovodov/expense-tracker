"""Тесты реестра расходов: добавление, отбор за месяц и по категории, суммы."""

from datetime import date

import allure
import pytest

from expense_tracker.ledger import (
    Expense,
    Ledger,
    new_expense,
    summary,
    total,
    totals_by_category,
)


@allure.feature("Реестр расходов")
@allure.story("Новый расход")
class TestNewExpense:

    @allure.title("Расход хранит дату, категорию в нижнем регистре и сумму")
    def test_fields(self):
        expense = new_expense("2026-11-24", "Еда", "350,50", "Обед")
        assert expense == Expense(date(2026, 11, 24), "еда", 350.5, "Обед")

    @allure.title("Нулевая и отрицательная сумма отклоняются")
    def test_non_positive_amount_is_rejected(self):
        for amount in ("0", "-100"):
            with pytest.raises(ValueError, match="больше нуля"):
                new_expense("2026-11-24", "еда", amount)

    @allure.title("Дата не в формате ГГГГ-ММ-ДД отклоняется")
    def test_wrong_date_is_rejected(self):
        with pytest.raises(ValueError, match="ГГГГ-ММ-ДД"):
            new_expense("24.11.2026", "еда", "100")


@allure.feature("Реестр расходов")
@allure.story("Список расходов")
class TestLedgerAdd:

    @allure.title("Добавленный расход появляется в списке")
    def test_add(self):
        ledger = Ledger()
        expense = new_expense("2026-11-24", "еда", "350.50")
        ledger.add(expense)
        assert ledger.expenses == [expense]

    @allure.title("Категории «Еда» и «еда» — это одна категория")
    def test_category_ignores_case(self):
        ledger = Ledger()
        ledger.add(new_expense("2026-11-01", "Еда", "100"))
        ledger.add(new_expense("2026-11-02", "еда", "200"))
        assert totals_by_category(ledger.expenses) == {"еда": 300.0}


@allure.feature("Реестр расходов")
@allure.story("Отбор расходов")
class TestLedgerFilters:

    @allure.title("За месяц отбираются только расходы этого месяца")
    def test_in_month(self, expenses):
        selected = Ledger(expenses).in_month(2026, 11)
        assert [expense.comment for expense in selected] == ["Обед", "Метро", "Продукты"]

    @allure.title("Первый и последний день месяца входят в отчёт месяца")
    def test_month_boundaries(self, expenses):
        days = [expense.date.day for expense in Ledger(expenses).in_month(2026, 11)]
        assert days == [1, 15, 30]

    @allure.title("По категории отбираются расходы только этой категории")
    def test_in_category(self, expenses):
        selected = Ledger(expenses).in_category("ЕДА")
        assert [expense.amount for expense in selected] == [350.5, 1200.0, 410.99]

    @allure.title("Неизвестная категория даёт пустой список")
    def test_unknown_category(self, expenses):
        assert Ledger(expenses).in_category("путешествия") == []


@allure.feature("Реестр расходов")
@allure.story("Суммы")
class TestLedgerTotals:

    @allure.title("Общая сумма равна сумме всех расходов")
    def test_total(self, expenses):
        assert total(expenses) == pytest.approx(2021.49)

    @allure.title("Суммы считаются отдельно по каждой категории")
    def test_totals_by_category(self, expenses):
        expected = {"еда": pytest.approx(1961.49), "транспорт": pytest.approx(60.0)}
        assert totals_by_category(expenses) == expected

    @allure.title("Отчёт за месяц перечисляет категории и строку «Всего»")
    def test_summary(self, expenses):
        with allure.step("Отобрать расходы за ноябрь 2026 года"):
            november = Ledger(expenses).in_month(2026, 11)

        with allure.step("Построить отчёт по отобранным расходам"):
            report = summary(november, "Расходы за 2026-11")
        allure.attach(report, name="Отчёт за ноябрь", attachment_type=allure.attachment_type.TEXT)

        with allure.step("Проверить, что в отчёте есть каждая категория и общая сумма"):
            assert "еда:" in report
            assert "транспорт:" in report
            assert "Всего:" in report
