"""Хранение реестра в файле JSON и обмен расходами через файлы CSV."""

import csv
import json
from datetime import date
from pathlib import Path

from .ledger import Expense, Ledger, new_expense

CSV_HEADER = ["date", "category", "amount", "comment"]


def save_json(ledger: Ledger, path: Path) -> None:
    """Сохраняет расходы реестра в файл JSON."""
    records = [
        {
            "date": expense.date.isoformat(),
            "category": expense.category,
            "amount": expense.amount,
            "comment": expense.comment,
        }
        for expense in ledger.expenses
    ]
    Path(path).write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


def load_json(path: Path) -> Ledger:
    """Читает расходы из файла JSON. Если файла нет, реестр пуст."""
    path = Path(path)
    if not path.exists():
        return Ledger()
    records = json.loads(path.read_text(encoding="utf-8"))
    return Ledger(
        Expense(
            date.fromisoformat(record["date"]),
            record["category"],
            float(record["amount"]),
            record.get("comment", ""),
        )
        for record in records
    )


def export_csv(ledger: Ledger, path: Path) -> None:
    """Записывает расходы реестра в файл CSV."""
    with open(path, "w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(CSV_HEADER)
        for expense in ledger.expenses:
            writer.writerow(
                [expense.date.isoformat(), expense.category, expense.amount, expense.comment]
            )


def import_csv(ledger: Ledger, path: Path) -> int:
    """Добавляет в реестр расходы из файла CSV и возвращает их количество."""
    with open(path, encoding="utf-8", newline="") as file:
        rows = list(csv.DictReader(file))
    for row in rows:
        ledger.add(new_expense(row["date"], row["category"], row["amount"], row["comment"]))
    return len(rows)
