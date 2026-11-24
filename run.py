"""Запускает автотесты проекта.

Что делает:
1. создаёт виртуальное окружение в папке `.venv`, если его ещё нет;
2. устанавливает зависимости из `requirements.txt`, если они ещё не установлены;
3. запускает pytest. Результаты для Allure TestOps пишутся в папку `allure-results`.

Запуск из папки проекта:  python run.py   (на Windows:  py run.py)
"""

import hashlib
import os
import subprocess
import sys
from pathlib import Path

MINIMUM_PYTHON = (3, 10)
ALL_PASSED = 0
SOME_FAILED = 1
FAILED_TO_START = 2

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
BINARIES = VENV / ("Scripts" if os.name == "nt" else "bin")
PYTHON = BINARIES / ("python.exe" if os.name == "nt" else "python")
REQUIREMENTS = ROOT / "requirements.txt"
INSTALLED = VENV / "installed-requirements.sha256"
RESULTS = ROOT / "allure-results"


def requirements_digest() -> str:
    """Отпечаток файла requirements.txt, по нему скрипт узнаёт, менялся ли файл."""
    return hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()


def create_venv() -> bool:
    """Создаёт виртуальное окружение. Возвращает True, если окружение готово."""
    if PYTHON.exists():
        return True
    print("Создаю виртуальное окружение — это нужно один раз.", flush=True)
    created = subprocess.run([sys.executable, "-m", "venv", str(VENV)])
    if created.returncode == 0 and PYTHON.exists():
        return True
    print("Не удалось создать виртуальное окружение.", file=sys.stderr)
    if sys.platform.startswith("linux"):
        print(
            "В Linux для этого нужен пакет python3-venv, например: sudo apt install python3-venv",
            file=sys.stderr,
        )
    return False


def install_dependencies() -> bool:
    """Устанавливает зависимости, если requirements.txt менялся с прошлой установки."""
    digest = requirements_digest()
    if INSTALLED.exists() and INSTALLED.read_text(encoding="utf-8") == digest:
        return True
    print("Устанавливаю зависимости — это нужно один раз.", flush=True)
    command = [str(PYTHON), "-m", "pip", "install", "--disable-pip-version-check", "-r", str(REQUIREMENTS)]
    if subprocess.run(command, cwd=ROOT).returncode != 0:
        print(
            "Не удалось установить зависимости. Проверьте подключение к интернету "
            "и запустите скрипт ещё раз.",
            file=sys.stderr,
        )
        return False
    INSTALLED.write_text(digest, encoding="utf-8")
    return True


def describe_result(returncode: int) -> None:
    """Объясняет итог запуска в одну строку."""
    if returncode == ALL_PASSED:
        print("\nВсе тесты прошли.")
    elif returncode == SOME_FAILED:
        print(
            "\nНекоторые тесты упали. Для ветки main это ожидаемо: "
            "известные дефекты проекта перечислены в README."
        )
    else:
        print("\nТесты не смогли запуститься. Причина — в тексте выше.")


def main() -> int:
    """Возвращает код завершения pytest."""
    if sys.version_info < MINIMUM_PYTHON:
        version = ".".join(str(part) for part in sys.version_info[:3])
        print(
            f"Нужен Python {MINIMUM_PYTHON[0]}.{MINIMUM_PYTHON[1]} или новее, сейчас запущен {version}.",
            file=sys.stderr,
        )
        return FAILED_TO_START
    if not create_venv() or not install_dependencies():
        return FAILED_TO_START

    print("Запускаю автотесты.", flush=True)
    returncode = subprocess.run([str(PYTHON), "-m", "pytest"], cwd=ROOT).returncode
    describe_result(returncode)
    if RESULTS.is_dir():
        print(f"Результаты для Allure TestOps лежат в папке {RESULTS}")
        print("Чтобы отправить их в Allure TestOps, запустите: python upload.py")
    return returncode


if __name__ == "__main__":
    sys.exit(main())
