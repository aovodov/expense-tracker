"""Поднимает локальный Jenkins и связывает его с Allure TestOps.

Что делает:
1. скачивает плагин ТестОпса и собирает небольшой образ Jenkins (нужен Docker);
2. запускает контейнер: администратор, сервер ТестОпса и джоба «practice» уже настроены;
3. создаёт в ТестОпсе интеграцию Jenkins и подключает её к проекту;
4. запускает первую сборку — по её результатам джоба появляется в ТестОпсе;
5. помечает джобу «можно использовать для запуска тестов».

После этого автотесты можно запускать прямо из ТестОпса:
Тест-кейсы → выберите автотесты → Запустить → Джобы → Отправить.

Запуск из папки проекта:  python ci.py   (на Windows:  py ci.py)
"""

import argparse
import base64
import http.cookiejar
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.sax.saxutils
from pathlib import Path

from upload import ask_connection_settings, save_settings

ROOT = Path(__file__).resolve().parent
CI = ROOT / "ci"
BUILD = ROOT / ".ci" / "build"

# Крошка Jenkins действительна вместе с cookie сессии, поэтому все запросы
# к Jenkins идут через один opener с общим cookie-jar.
JENKINS_OPENER = urllib.request.build_opener(
    urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
)

IMAGE = "expense-tracker-jenkins"
CONTAINER = "expense-tracker-jenkins"
VOLUME = "expense-tracker-jenkins-data"
DEFAULT_PORT = 8090
JENKINS_USER = "admin"
DEFAULT_JENKINS_PASSWORD = "JenkinsPractice123"
INTEGRATION_NAME = "Практикум Jenkins"
JOB_NAME = "practice"
SERVER_ID = "testops"
CREDENTIAL_ID = "testops-token"
PLUGIN_URL = "https://dl.qatools.ru/repository/public/qatools-jenkins-plugin/qatools-jenkins-plugin-4.2.1.hpi"
BOOT_TIMEOUT_SECONDS = 180
BUILD_TIMEOUT_SECONDS = 600
JOB_TIMEOUT_SECONDS = 120

PLUGIN_CONFIG_XML = """<io.qameta.allure.jenkins.config.AllurePluginConfig>
  <serverConfigs>
    <io.qameta.allure.jenkins.config.AllureServerConfig>
      <id>__SERVER_ID__</id>
      <endpoint>__ENDPOINT__</endpoint>
      <credentialsId>__CREDENTIAL_ID__</credentialsId>
      <enableSslValidation>false</enableSslValidation>
      <enabled>true</enabled>
      <threadsCount>2</threadsCount>
      <batchSize>25</batchSize>
      <maxDepth>1</maxDepth>
      <processInterval>2</processInterval>
      <indexInterval>1</indexInterval>
      <delayInterval>2</delayInterval>
    </io.qameta.allure.jenkins.config.AllureServerConfig>
  </serverConfigs>
</io.qameta.allure.jenkins.config.AllurePluginConfig>
"""

PIPELINE = """pipeline {
  agent any
  stages {
    stage('Код проекта') {
      steps {
        sh 'rsync -a --exclude .venv --exclude .git --exclude allure-results --exclude .ci --exclude __pycache__ --exclude .pytest_cache /home/project/ ./'
      }
    }
    stage('Автотесты') {
      steps {
        withAllureUpload(
          serverId: '__SERVER_ID__',
          projectId: '__PROJECT_ID__',
          name: 'Jenkins',
          results: [[path: 'allure-results']],
          indexExistingFiles: true
        ) {
          sh 'python3 run.py'
        }
      }
    }
  }
}"""

JOB_CONFIG_XML = """<?xml version="1.1" encoding="UTF-8"?>
<flow-definition>
  <description>Практикум «Учёт расходов»: автотесты с загрузкой результатов в ТестОпс</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition">
    <script>__SCRIPT__</script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Поднимает локальный Jenkins и связывает его с Allure TestOps.")
    parser.add_argument("--endpoint", help="адрес инстанса Allure TestOps, например https://testops.example.com")
    parser.add_argument("--project-id", help="ID проекта в Allure TestOps")
    parser.add_argument("--token", help="API-токен (безопаснее задавать переменной окружения ALLURE_TOKEN)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"порт Jenkins на вашей машине (по умолчанию {DEFAULT_PORT})")
    parser.add_argument(
        "--password",
        default=DEFAULT_JENKINS_PASSWORD,
        help="пароль администратора Jenkins, по умолчанию используется пароль из практикума",
    )
    parser.add_argument("--hpi", help="свой файл плагина ТестОпса (.hpi), например собранный из исходников")
    parser.add_argument("--skip-build", action="store_true", help="не запускать первую сборку и не помечать джобу")
    parser.add_argument("--keep", action="store_true", help="не пересоздавать контейнер и данные Jenkins")
    return parser.parse_args()


def docker(*arguments: str, check: bool = True) -> str:
    result = subprocess.run(["docker", *arguments], capture_output=True, text=True)
    if check and result.returncode != 0:
        sys.exit(f"Команда docker {' '.join(arguments)} не удалась:\n{result.stderr.strip()}")
    return result.stdout.strip()


def ensure_docker() -> None:
    version = docker("version", "--format", "{{.Server.Version}}", check=False)
    if not version:
        sys.exit("Не удалось обратиться к Docker. Запустите Docker Desktop и повторите.")
    print(f"Docker {version}")


def api(endpoint: str, token: str, method: str, path: str, body=None):
    """Запрос к API ТестОпса по API-токену."""
    request = urllib.request.Request(f"{endpoint}/api{path}", method=method)
    request.add_header("Authorization", f"Api-Token {token}")
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, data, timeout=30) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"ТестОпс ответил ошибкой на {method} /api{path}: HTTP {e.code}\n{detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"ТестОпс недоступен ({method} /api{path}): {e.reason}") from None
    return json.loads(text) if text.strip() else {}


def page_items(page) -> list:
    """Элементы страницы ответа API независимо от имени поля со списком."""
    if isinstance(page, dict):
        for key in ("content", "items", "models", "results"):
            if isinstance(page.get(key), list):
                return page[key]
    return []


def container_endpoint(endpoint: str) -> str:
    """Адрес ТестОпса, по которому до него доберётся контейнер Jenkins."""
    parts = urllib.parse.urlsplit(endpoint)
    host = parts.hostname
    if host in ("localhost", "127.0.0.1"):
        host = "host.docker.internal"
    netloc = f"{host}:{parts.port}" if parts.port else host
    return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path.rstrip("/"), "", ""))


def jenkins_request(port: int, password: str, method: str, path: str, body=None, crumb=None):
    """Запрос к Jenkins от имени администратора. Крошка и сессия живут в общем cookie-jar."""
    request = urllib.request.Request(f"http://localhost:{port}{path}", method=method)
    encoded = base64.b64encode(f"{JENKINS_USER}:{password}".encode()).decode()
    request.add_header("Authorization", f"Basic {encoded}")
    if crumb is not None:
        request.add_header(crumb[0], crumb[1])
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        request.add_header("Content-Type", "application/json")
    try:
        with JENKINS_OPENER.open(request, data, timeout=30) as response:
            text = response.read().decode()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        raise RuntimeError(f"Jenkins ответил ошибкой на {method} {path}: HTTP {e.code}\n{detail}") from None
    return json.loads(text) if text.strip() else {}


def download_plugin(destination: Path, source: str) -> Path:
    if destination.exists():
        return destination
    print("Скачиваю плагин ТестОпса для Jenkins — это нужно один раз.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    try:
        with urllib.request.urlopen(source, timeout=300) as response, open(partial, "wb") as file:
            shutil.copyfileobj(response, file)
    except OSError as e:
        sys.exit(
            f"Не удалось скачать плагин ({e}). Скачайте вручную {source}\n"
            f"и укажите файл параметром --hpi."
        )
    partial.replace(destination)
    return destination


def render_context(project_id: int, endpoint_inside: str, hpi: Path) -> None:
    """Готовит каталог для docker build: плагин, преднастройка и джоба с вашим ID проекта."""
    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir(parents=True)
    shutil.copy(CI / "Dockerfile.jenkins", BUILD / "Dockerfile")
    shutil.copy(CI / "plugins.txt", BUILD / "plugins.txt")
    shutil.copy(CI / "jenkins.yaml", BUILD / "jenkins.yaml")
    shutil.copy(hpi, BUILD / "testops-jenkins.hpi")

    plugin_config = (
        PLUGIN_CONFIG_XML.replace("__SERVER_ID__", SERVER_ID)
        .replace("__CREDENTIAL_ID__", CREDENTIAL_ID)
        .replace("__ENDPOINT__", endpoint_inside)
    )
    # имя файла — id глобальной конфигурации плагина, а не имя класса
    (BUILD / "allure-config.xml").write_text(plugin_config, encoding="utf-8")

    pipeline = PIPELINE.replace("__SERVER_ID__", SERVER_ID).replace("__PROJECT_ID__", str(project_id))
    job_config = JOB_CONFIG_XML.replace("__SCRIPT__", xml.sax.saxutils.escape(pipeline))
    job_dir = BUILD / "jobs" / JOB_NAME
    job_dir.mkdir(parents=True)
    (job_dir / "config.xml").write_text(job_config, encoding="utf-8")


def build_image() -> None:
    print("Собираю образ Jenkins с плагином ТестОпса — в первый раз это занимает несколько минут.")
    result = subprocess.run(["docker", "build", "-t", IMAGE, str(BUILD)], capture_output=True, text=True)
    if result.returncode != 0:
        tail = (result.stdout + result.stderr)[-3000:]
        sys.exit(f"Не удалось собрать образ Jenkins:\n{tail}")


def start_container(port: int, password: str, token: str, keep: bool) -> None:
    if not keep:
        docker("rm", "-f", CONTAINER, check=False)
        docker("volume", "rm", "-f", VOLUME, check=False)
    docker(
        "run", "-d", "--name", CONTAINER,
        "-p", f"127.0.0.1:{port}:8080",
        "--add-host=host.docker.internal:host-gateway",
        "-v", f"{ROOT}:/home/project:ro",
        "-v", f"{VOLUME}:/var/jenkins_home",
        "-e", f"JENKINS_ADMIN_PASSWORD={password}",
        "-e", f"TESTOPS_TOKEN={token}",
        "-e", "JAVA_OPTS=-Djenkins.install.RunSetupWizard=false",
        IMAGE,
    )


def wait_jenkins(port: int, password: str) -> None:
    print("Жду, пока Jenkins запустится — около минуты.")
    deadline = time.time() + BOOT_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            jenkins_request(port, password, "GET", "/api/json")
            return
        except (RuntimeError, OSError):
            # пока Jenkins поднимается, соединение то отклоняется, то обрывается
            time.sleep(3)
    sys.exit(f"Jenkins не запустился за {BOOT_TIMEOUT_SECONDS // 60} минут. Логи: docker logs {CONTAINER}")


def ensure_integration(testops, name: str, jenkins_url: str, password: str) -> int:
    for item in page_items(testops("GET", "/integration?pageSize=200")):
        if item.get("name") == name and item.get("type") == "jenkins":
            print(f"Интеграция «{name}» в ТестОпсе уже есть, использую её.")
            return item["id"]
    created = testops("POST", "/integration", {
        "name": name,
        "type": "jenkins",
        "settings": {"endpoint": jenkins_url},
        "globalSecret": {"username": JENKINS_USER, "apiToken": password},
    })
    print(f"Создал интеграцию «{name}» в ТестОпсе.")
    return created["id"]


def ensure_project_link(testops, project_id: int, integration_id: int) -> None:
    linked = page_items(testops("GET", f"/integration/{integration_id}/project"))
    if any(int(item.get("id", 0)) == project_id for item in linked):
        return
    testops("POST", "/integration/project", {"integrationId": integration_id, "projectId": project_id})
    print("Подключил интеграцию к проекту.")


def trigger_first_build(port: int, password: str) -> None:
    crumb = jenkins_request(port, password, "GET", "/crumbIssuer/api/json")
    jenkins_request(port, password, "POST", f"/job/{JOB_NAME}/build", crumb=(crumb["crumbRequestField"], crumb["crumb"]))
    print("Запустил первую сборку — по ней джоба появится в ТестОпсе.")


def wait_build(port: int, password: str) -> None:
    print("Первая сборка идёт: окружение, автотесты, загрузка результатов. Это пара минут.")
    deadline = time.time() + BUILD_TIMEOUT_SECONDS
    while time.time() < deadline:
        try:
            info = jenkins_request(port, password, "GET", f"/job/{JOB_NAME}/lastBuild/api/json")
            if info.get("result") is not None:
                print(f"Сборка №{info['number']} закончилась со статусом {info['result']}.")
                return
        except RuntimeError:
            pass
        time.sleep(5)
    sys.exit(f"Сборка не закончилась за {BUILD_TIMEOUT_SECONDS // 60} минут. Смотрите: http://localhost:{port}")


def find_job(testops, project_id: int):
    for path in (f"/job?projectId={project_id}&pageSize=200", "/job?pageSize=200"):
        try:
            page = testops("GET", path)
        except RuntimeError:
            continue
        for job in page_items(page):
            if int(job.get("projectId", 0)) == project_id and job.get("externalId") == JOB_NAME:
                return job
    return None


def wait_job_in_testops(testops, project_id: int):
    deadline = time.time() + JOB_TIMEOUT_SECONDS
    while time.time() < deadline:
        job = find_job(testops, project_id)
        if job is not None:
            return job
        time.sleep(5)
    sys.exit(f"Джоба «{JOB_NAME}» не появилась в ТестОпсе за {JOB_TIMEOUT_SECONDS} секунд.")


def allow_job_runs(testops, project_id: int, integration_id: int) -> None:
    job = wait_job_in_testops(testops, project_id)
    # джоба, созданная плагином при первой загрузке, приходит без привязки к интеграции
    testops("PATCH", f"/job/{job['id']}", {
        "integrationId": job.get("integrationId") or integration_id,
        "externalId": job.get("externalId"),
        "name": job.get("name"),
        "canRun": True,
        "parameters": job.get("parameters") or [],
    })
    print(f"Джоба «{JOB_NAME}» помечена «можно использовать для запуска тестов».")


def main() -> int:
    args = parse_args()
    ensure_docker()
    endpoint, project_id, token = ask_connection_settings(args)
    testops = lambda method, path, body=None: api(endpoint, token, method, path, body)  # noqa: E731

    password = args.password
    hpi = Path(args.hpi) if args.hpi else download_plugin(ROOT / ".ci" / "testops-jenkins.hpi", PLUGIN_URL)
    render_context(project_id, container_endpoint(endpoint), hpi)
    build_image()
    start_container(args.port, password, token, args.keep)
    wait_jenkins(args.port, password)

    integration_id = ensure_integration(testops, INTEGRATION_NAME, f"http://localhost:{args.port}", password)
    ensure_project_link(testops, project_id, integration_id)
    if not args.skip_build:
        trigger_first_build(args.port, password)
        wait_build(args.port, password)
        allow_job_runs(testops, project_id, integration_id)

    save_settings(endpoint, project_id)
    print()
    print("Готово.")
    print(f"Jenkins: http://localhost:{args.port}  (логин {JENKINS_USER}, пароль {password})")
    print("Попробуйте: ТестОпс → Тест-кейсы → выберите автотесты → Запустить → Джобы → Отправить.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
