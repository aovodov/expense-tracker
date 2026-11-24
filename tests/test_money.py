"""Тесты сумм денег: разбор строки и вывод на экран."""

import allure
import pytest

from expense_tracker.money import format_amount, parse_amount


@allure.feature("Деньги")
@allure.story("Чтение суммы")
class TestParseAmount:

    @allure.title("Сумма с точкой читается: «12.50» — это 12.5 руб.")
    def test_dot(self):
        assert parse_amount("12.50") == 12.5

    @allure.title("Сумма с запятой читается так же: «12,50» — это 12.5 руб.")
    def test_comma(self):
        assert parse_amount("12,50") == 12.5

    @allure.title("Целая сумма читается: «100» — это 100 руб.")
    def test_integer(self):
        assert parse_amount("100") == 100.0

    @allure.title("Текст вместо суммы — ошибка с понятным сообщением")
    def test_text_is_rejected(self):
        with pytest.raises(ValueError, match="Сумма должна быть числом"):
            parse_amount("двенадцать")


@allure.feature("Деньги")
@allure.story("Вывод суммы")
@allure.severity(allure.severity_level.CRITICAL)
class TestFormatAmount:

    @allure.title("Сумма выводится ровно с двумя знаками после запятой")
    def test_two_decimal_places(self):
        assert format_amount(12.5) == "12.50 руб.", (
            f"Ожидалось «12.50 руб.», получено «{format_amount(12.5)}»: "
            "у суммы должно быть два знака после запятой"
        )
