"""Загружает результаты автотестов в Allure TestOps.

Что делает:
1. находит утилиту allurectl: берёт уже установленную, а если её нет — скачивает
   официальную с github.com/allure-framework/allurectl в папку `.tools`;
2. спрашивает недостающие параметры: адрес Allure TestOps, API-токен и ID проекта;
3. запускает `allurectl upload`.

Запуск из папки проекта:  python upload.py   (на Windows:  py upload.py)

Параметры можно задать заранее, тогда вопросов не будет:
  аргументами:           python upload.py --endpoint https://testops.example.com --project-id 124
  переменными окружения: ALLURE_ENDPOINT, ALLURE_TOKEN, ALLURE_PROJECT_ID
"""

import argparse
import getpass
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
import warnings
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RESULTS = ROOT / "allure-results"
TOOLS = ROOT / ".tools"
SETTINGS = ROOT / ".testops.json"
ALLURECTL = TOOLS / ("allurectl.exe" if os.name == "nt" else "allurectl")
RELEASES = "https://github.com/allure-framework/allurectl/releases"
SYSTEMS = ("windows", "darwin", "linux")
ARCHITECTURES = {"x86_64": "amd64", "amd64": "amd64", "arm64": "arm64", "aarch64": "arm64"}
EXIT_NOT_CONFIGURED = 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Загружает результаты автотестов в Allure TestOps.")
    parser.add_argument("--endpoint", help="адрес инстанса Allure TestOps, например https://testops.example.com")
    parser.add_argument("--project-id", help="ID проекта в Allure TestOps")
    parser.add_argument("--token", help="API-токен (безопаснее задавать переменной окружения ALLURE_TOKEN)")
    parser.add_argument("--launch-name", help="название запуска")
    parser.add_argument(
        "--check",
        action="store_true",
        help="только скачать allurectl и показать его версию, ничего не загружать",
    )
    return parser.parse_args()


def allurectl_asset_name() -> str:
    """Имя файла allurectl в релизе на GitHub для этой операционной системы и процессора."""
    system = platform.system().lower()
    architecture = ARCHITECTURES.get(platform.machine().lower())
    if system not in SYSTEMS or architecture is None:
        sys.exit(
            f"Не удалось подобрать allurectl для {platform.system()} {platform.machine()}. "
            f"Скачайте утилиту вручную со страницы {RELEASES} "
            f"и положите в папку {TOOLS} под именем allurectl."
        )
    name = f"allurectl_{system}_{architecture}"
    return f"{name}.exe" if system == "windows" else name


def find_allurectl() -> Path | None:
    """Ищет уже скачанную утилиту в папке проекта или в PATH."""
    if ALLURECTL.exists():
        return ALLURECTL
    on_path = shutil.which("allurectl")
    return Path(on_path) if on_path else None


def is_working(allurectl: Path) -> bool:
    """Проверяет, что файл утилиты запускается."""
    return subprocess.run([str(allurectl), "--version"], capture_output=True).returncode == 0


def download_allurectl() -> Path:
    """Скачивает свежий релиз allurectl с официальной страницы на GitHub."""
    url = f"{RELEASES}/latest/download/{allurectl_asset_name()}"
    print("Скачиваю allurectl — это нужно один раз.", flush=True)
    TOOLS.mkdir(exist_ok=True)
    partial = ALLURECTL.with_name(ALLURECTL.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as response, open(partial, "wb") as file:
        shutil.copyfileobj(response, file)
    partial.replace(ALLURECTL)
    if os.name != "nt":
        ALLURECTL.chmod(0o755)
    return ALLURECTL


def ensure_allurectl() -> Path:
    """Возвращает путь к рабочей утилите allurectl, скачивая её при необходимости."""
    found = find_allurectl()
    if found is not None and is_working(found):
        return found
    downloaded = download_allurectl()
    if not is_working(downloaded):
        sys.exit(
            f"Файл {downloaded} не запускается. Скачайте allurectl вручную "
            f"со страницы {RELEASES} и положите его в папку {TOOLS}."
        )
    return downloaded


def load_settings() -> dict:
    """Читает адрес и ID проекта, сохранённые при прошлой успешной загрузке."""
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    return {}


def save_settings(endpoint: str, project_id: int) -> None:
    """Запоминает адрес и ID проекта, чтобы не спрашивать их в следующий раз."""
    settings = {"endpoint": endpoint, "project_id": project_id}
    SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def normalize_endpoint(text: str) -> str:
    """Дополняет адрес протоколом и убирает косую черту в конце."""
    endpoint = text.strip().rstrip("/")
    if not endpoint.startswith(("http://", "https://")):
        endpoint = f"https://{endpoint}"
    return endpoint


def parse_project_id(text: str) -> int | None:
    """Понимает как число, так и адрес страницы проекта вида https://…/project/124/…"""
    match = re.search(r"/project/(\d+)", text) or re.fullmatch(r"\s*(\d+)\s*", text)
    return int(match.group(1)) if match else None


def current_branch() -> str | None:
    """Имя текущей ветки. Если проект скачан без Git, возвращает None."""
    head = ROOT / ".git" / "HEAD"
    if not head.exists():
        return None
    match = re.fullmatch(r"ref: refs/heads/(.+)", head.read_text(encoding="utf-8").strip())
    return match.group(1) if match else None


def default_launch_name(branch: str | None) -> str:
    where = f"ветка {branch}, " if branch else ""
    return f"Локальный запуск: {where}{datetime.now():%Y-%m-%d %H:%M}"


def ask(question: str) -> str:
    """Задаёт вопрос и ждёт непустого ответа."""
    answer = ""
    while not answer:
        answer = input(f"{question}: ").strip()
    return answer


def ask_token() -> str:
    """Спрашивает API-токен. Введённый текст не показывается на экране."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", getpass.GetPassWarning)
        token = ""
        while not token:
            token = getpass.getpass("API-токен (ввод не отображается): ").strip()
    return token


def ask_project_id() -> int:
    project_id = parse_project_id(ask("ID проекта"))
    while project_id is None:
        print("Нужно число, например 124. Оно есть в адресе страницы проекта, после /project/.")
        project_id = parse_project_id(ask("ID проекта"))
    return project_id


def has_results() -> bool:
    return any(RESULTS.glob("*-result.json"))


def upload(allurectl: Path, endpoint: str, token: str, project_id: int, name: str, tags: str) -> int:
    """Запускает allurectl upload и возвращает его код завершения."""
    command = [
        str(allurectl),
        "upload",
        f"--endpoint={endpoint}",
        f"--project-id={project_id}",
        f"--launch-name={name}",
        f"--launch-tags={tags}",
        str(RESULTS),
    ]
    # Токен передаётся переменной окружения, чтобы его не было видно в списке процессов.
    environment = dict(os.environ, ALLURE_TOKEN=token)
    return subprocess.run(command, cwd=ROOT, env=environment).returncode


def ask_connection_settings(args: argparse.Namespace) -> tuple[str, int, str]:
    """Собирает адрес TestOps, ID проекта и токен: из аргументов, окружения, файла или вопросов."""
    settings = load_settings()
    endpoint_text = args.endpoint or os.environ.get("ALLURE_ENDPOINT") or settings.get("endpoint")
    project_text = args.project_id or os.environ.get("ALLURE_PROJECT_ID")
    project_text = project_text or str(settings.get("project_id", ""))
    token = args.token or os.environ.get("ALLURE_TOKEN")

    missing_something = not (endpoint_text and project_text and token)
    if missing_something and not sys.stdin.isatty():
        print(
            "Не хватает параметров, а скрипт запущен не из терминала. Задайте их переменными "
            "окружения: ALLURE_ENDPOINT, ALLURE_TOKEN, ALLURE_PROJECT_ID.",
            file=sys.stderr,
        )
        sys.exit(EXIT_NOT_CONFIGURED)

    endpoint_text = endpoint_text or ask("Адрес Allure TestOps, например https://testops.example.com")
    project_id = parse_project_id(project_text) or ask_project_id()
    return normalize_endpoint(endpoint_text), project_id, token or ask_token()


def main() -> int:
    args = parse_args()
    try:
        allurectl = ensure_allurectl()
    except OSError as error:
        print(f"Не удалось скачать allurectl: {error}", file=sys.stderr)
        return 2
    if args.check:
        version = subprocess.run([str(allurectl), "--version"], capture_output=True, text=True)
        print(f"allurectl готов: {allurectl}\n{version.stdout.strip()}")
        return 0
    if not has_results():
        print(f"В папке {RESULTS} нет результатов. Сначала запустите тесты: python run.py", file=sys.stderr)
        return 2

    endpoint, project_id, token = ask_connection_settings(args)
    branch = current_branch()
    launch_name = args.launch_name or default_launch_name(branch)
    launch_tags = "local" + (f",{branch}" if branch else "")
    print(f"Загружаю результаты в проект {project_id}, запуск «{launch_name}».", flush=True)
    returncode = upload(allurectl, endpoint, token, project_id, launch_name, launch_tags)
    if returncode != 0:
        print("Загрузка не удалась. Причина — в сообщении allurectl выше.", file=sys.stderr)
        return returncode
    save_settings(endpoint, project_id)
    print("Готово. Отчёт о запуске — по ссылке в строке «Report link» выше.")
    print("Все запуски — в Allure TestOps, в разделе «Запуски» проекта.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
