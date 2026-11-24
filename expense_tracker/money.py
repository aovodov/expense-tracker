"""Суммы денег: разбор строки, которую ввёл пользователь, и вывод на экран."""


def parse_amount(text: str) -> float:
    """Превращает строку вида «12.50» или «12,50» в число рублей."""
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"Сумма должна быть числом, получено «{text}»") from None


def format_amount(amount: float) -> str:
    """Выводит сумму с двумя знаками после запятой: 12.5 превращается в «12.50 руб.»."""
    return f"{amount} руб."
