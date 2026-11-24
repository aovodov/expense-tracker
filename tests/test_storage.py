"""Тесты хранения: файл JSON и файлы CSV."""

from pathlib import Path

import allure

from expense_tracker.ledger import Ledger
from expense_tracker.storage import export_csv, import_csv, load_json, save_json

CSV_HEADER = "date,category,amount,comment\n"


def write_csv(path: Path, rows: list[str]) -> Path:
    """Создаёт файл CSV с заголовком и строками расходов."""
    path.write_text(CSV_HEADER + "".join(f"{row}\n" for row in rows), encoding="utf-8")
    return path


@allure.feature("Файлы")
@allure.story("Файл JSON")
class TestJsonStorage:

    @allure.title("Расходы сохраняются в файл и читаются обратно без изменений")
    def test_round_trip(self, tmp_path, expenses):
        path = tmp_path / "expenses.json"
        save_json(Ledger(expenses), path)
        assert load_json(path).expenses == expenses

    @allure.title("Если файла с данными нет, реестр пуст")
    def test_missing_file(self, tmp_path):
        assert load_json(tmp_path / "нет-такого-файла.json").expenses == []


@allure.feature("Файлы")
@allure.story("Экспорт в CSV")
class TestExportCsv:

    @allure.title("Файл CSV начинается со строки заголовка")
    def test_header(self, tmp_path, expenses):
        path = tmp_path / "expenses.csv"
        export_csv(Ledger(expenses), path)
        assert path.read_text(encoding="utf-8").startswith(CSV_HEADER)


@allure.feature("Файлы")
@allure.story("Импорт из CSV")
class TestImportCsv:

    @allure.title("Импортируются все строки файла, включая последнюю")
    def test_all_rows(self, tmp_path):
        path = write_csv(
            tmp_path / "expenses.csv",
            [
                "2026-11-01,еда,350.50,Обед",
                "2026-11-02,транспорт,60,Метро",
                "2026-11-03,еда,1200,Продукты",
            ],
        )
        ledger = Ledger()
        import_csv(ledger, path)
        assert len(ledger.expenses) == 3, (
            f"В файле 3 расхода, а импортировано {len(ledger.expenses)}: "
            "последняя строка файла теряется"
        )

    @allure.title("Сумма с запятой в файле CSV читается правильно")
    def test_comma_in_amount(self, tmp_path):
        path = write_csv(
            tmp_path / "expenses.csv",
            [
                '2026-11-01,еда,"12,50",Обед',
                "2026-11-02,транспорт,60,Метро",
            ],
        )
        ledger = Ledger()
        import_csv(ledger, path)
        assert ledger.expenses[0].amount == 12.5

    @allure.title("Файл только с заголовком даёт пустой реестр")
    def test_header_only(self, tmp_path):
        path = write_csv(tmp_path / "empty.csv", [])
        ledger = Ledger()
        import_csv(ledger, path)
        assert ledger.expenses == []
