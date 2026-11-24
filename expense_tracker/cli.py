"""Командная строка приложения «Учёт расходов»."""

import argparse
from datetime import date
from pathlib import Path

from .budget import budget_report
from .ledger import Expense, Ledger, new_expense, summary, total
from .money import format_amount
from .storage import export_csv, import_csv, load_json, save_json

TODAY = "today"
CHANGING_COMMANDS = ("add", "import")


def build_parser() -> argparse.ArgumentParser:
    """Описывает команды и их аргументы."""
    parser = argparse.ArgumentParser(
        prog="expense-tracker",
        description="Учёт расходов в командной строке.",
    )
    parser.add_argument(
        "--file",
        default="expenses.json",
        help="файл, в котором хранятся расходы (по умолчанию expenses.json)",
    )
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="добавить расход")
    add.add_argument("date", help=f"дата в формате ГГГГ-ММ-ДД или {TODAY}")
    add.add_argument("category", help="категория, например «еда»")
    add.add_argument("amount", help="сумма в рублях, например 350.50 или 350,50")
    add.add_argument("comment", nargs="?", default="", help="комментарий (необязательно)")

    show = commands.add_parser("list", help="показать расходы")
    show.add_argument("--month", help="только этот месяц, в формате ГГГГ-ММ")
    show.add_argument("--category", help="только эта категория")

    report = commands.add_parser("report", help="отчёт по расходам за месяц")
    report.add_argument("--month", required=True, help="месяц в формате ГГГГ-ММ")
    report.add_argument("--budget", type=float, help="бюджет на месяц, чтобы узнать остаток")

    export = commands.add_parser("export", help="сохранить расходы в файл CSV")
    export.add_argument("path", help="файл CSV")

    import_ = commands.add_parser("import", help="добавить расходы из файла CSV")
    import_.add_argument("path", help="файл CSV")
    return parser


def parse_month(text: str) -> tuple[int, int]:
    """Разбирает месяц в формате ГГГГ-ММ на год и номер месяца."""
    year, month = text.split("-")
    return int(year), int(month)


def select(ledger: Ledger, month: str | None, category: str | None) -> list[Expense]:
    """Отбирает расходы по месяцу и категории, если они указаны."""
    expenses = ledger.expenses
    if month:
        expenses = Ledger(expenses).in_month(*parse_month(month))
    if category:
        expenses = Ledger(expenses).in_category(category)
    return expenses


def run_add(ledger: Ledger, args: argparse.Namespace) -> None:
    date_text = date.today().isoformat() if args.date == TODAY else args.date
    expense = new_expense(date_text, args.category, args.amount, args.comment)
    ledger.add(expense)
    print(f"Добавлено: {expense.date.isoformat()} {expense.category} {format_amount(expense.amount)}")


def run_list(ledger: Ledger, args: argparse.Namespace) -> None:
    expenses = select(ledger, args.month, args.category)
    if not expenses:
        print("Расходов нет.")
        return
    for expense in expenses:
        comment = f"  {expense.comment}" if expense.comment else ""
        print(f"{expense.date.isoformat()}  {expense.category:<12} {format_amount(expense.amount):>14}{comment}")
    print(f"Всего: {format_amount(total(expenses))}")


def run_report(ledger: Ledger, args: argparse.Namespace) -> None:
    expenses = ledger.in_month(*parse_month(args.month))
    print(summary(expenses, f"Расходы за {args.month}"))
    if args.budget is not None:
        print(budget_report(total(expenses), args.budget))


def run_export(ledger: Ledger, args: argparse.Namespace) -> None:
    export_csv(ledger, Path(args.path))
    print(f"Экспортировано расходов: {len(ledger.expenses)}")


def run_import(ledger: Ledger, args: argparse.Namespace) -> None:
    count = import_csv(ledger, Path(args.path))
    print(f"Импортировано расходов: {count}")


COMMANDS = {
    "add": run_add,
    "list": run_list,
    "report": run_report,
    "export": run_export,
    "import": run_import,
}


def main(argv: list[str] | None = None) -> int:
    """Запускает команду и возвращает код завершения: 0 — успех, 1 — ошибка."""
    args = build_parser().parse_args(argv)
    ledger = load_json(Path(args.file))
    try:
        COMMANDS[args.command](ledger, args)
    except (OSError, ValueError) as error:
        print(f"Ошибка: {error}")
        return 1
    if args.command in CHANGING_COMMANDS:
        save_json(ledger, Path(args.file))
    return 0
