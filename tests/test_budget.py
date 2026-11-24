"""Тесты месячного бюджета."""

import allure

from expense_tracker.budget import budget_report, is_over_budget, remaining


@allure.feature("Бюджет")
@allure.story("Превышение бюджета")
@allure.severity(allure.severity_level.CRITICAL)
class TestOverBudget:

    @allure.title("Расходы меньше бюджета — бюджет не превышен")
    def test_below_budget(self):
        assert not is_over_budget(900.0, 1000.0)

    @allure.title("Расходы больше бюджета — бюджет превышен")
    def test_above_budget(self):
        assert is_over_budget(1100.0, 1000.0)

    @allure.title("Расходы равны бюджету — бюджет не превышен")
    def test_equal_to_budget(self):
        assert not is_over_budget(1000.0, 1000.0), (
            "Расходы точно равны бюджету, перерасхода нет — превышения быть не должно"
        )


@allure.feature("Бюджет")
@allure.story("Остаток бюджета")
class TestRemaining:

    @allure.title("Остаток — это бюджет минус расходы")
    def test_under_budget(self):
        assert remaining(300.0, 1000.0) == 700.0

    @allure.title("При перерасходе остаток отрицательный")
    def test_over_budget(self):
        assert remaining(1200.0, 1000.0) == -200.0


@allure.feature("Бюджет")
@allure.story("Сообщение о бюджете")
class TestBudgetReport:

    @allure.title("Пока деньги остались, сообщение говорит, сколько осталось")
    def test_money_left(self):
        assert budget_report(300.0, 1000.0).startswith("Осталось")

    @allure.title("При перерасходе сообщение говорит, на сколько превышен бюджет")
    def test_overspending(self):
        assert budget_report(1200.0, 1000.0).startswith("Бюджет превышен на")
