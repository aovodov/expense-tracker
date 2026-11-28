import base64
import getpass
import http.cookiejar
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener
from xml.sax.saxutils import escape

JENKINS_USER = "admin"
LOCAL_PASSWORD = "JenkinsPractice123"
JOB_NAME = "practice"
EXPECTED_RESULTS = 30


def prompt(setting, label, default=""):
    value = os.environ.get(setting)
    if value is None:
        value = input(f"{label} [{default}]: " if default else f"{label}: ").strip() or default
    if not value:
        raise ValueError(f"Укажите {label.lower()}.")
    return value


def validate_url(value):
    url = urlsplit(value)
    if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.query or url.fragment:
        raise ValueError("Введите URL с HTTP или HTTPS без учётных данных, запроса и фрагмента.")
    if url.scheme == "http" and url.hostname not in {"localhost", "127.0.0.1", "::1", "host.docker.internal"}:
        print(f"Используется HTTP для {url.hostname}.")
    return value.rstrip("/")


def request(opener, base, headers, method, path, body=None):
    payload = json.dumps(body).encode() if body is not None else b"" if method == "POST" else None
    req = Request(base + path, data=payload, headers=headers, method=method)
    with opener.open(req, timeout=15) as response:
        data = response.read()
    return json.loads(data) if data else None


def wait_for(label, check, timeout=180):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result is not None:
            return result
        time.sleep(2)
    raise RuntimeError(f"Истекло время ожидания: {label}.")


def configure_jenkins(home, testops_url, project_id, launch_name):
    job_dir = home / "jobs" / JOB_NAME
    job_dir.mkdir(parents=True, exist_ok=True)
    if (job_dir / "config.xml").exists():
        raise ValueError("Для нового демо-запуска укажите чистый том Jenkins.")

    plugin_config = f"""<io.qameta.allure.jenkins.config.AllurePluginConfig>
  <serverConfigs>
    <io.qameta.allure.jenkins.config.AllureServerConfig>
      <id>testops</id>
      <endpoint>{escape(testops_url)}</endpoint>
      <credentialsId>testops-token</credentialsId>
      <enableSslValidation>true</enableSslValidation>
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
    (home / "allure-config.xml").write_text(plugin_config, encoding="utf-8")
    pipeline = f"""pipeline {{
  agent any
  stages {{
    stage('Автотесты') {{
      steps {{
        sh 'cp -R /opt/jenkins-demo/project/. .'
        withAllureUpload(
          serverId: 'testops',
          projectId: '{project_id}',
          name: '{launch_name}',
          results: [[path: 'allure-results']],
          indexExistingFiles: true
        ) {{
          sh '/opt/jenkins-demo/venv/bin/python -m pytest'
        }}
      }}
    }}
  }}
}}"""
    (job_dir / "config.xml").write_text(f"""<flow-definition>
  <description>Практикум TestOps</description>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition">
    <script>{escape(pipeline)}</script>
    <sandbox>true</sandbox>
  </definition>
</flow-definition>
""", encoding="utf-8")


def register_integration(testops, project_id, jenkins_url, password):
    name = f"Демо Jenkins · {project_id} · {jenkins_url}"
    credentials = {"username": JENKINS_USER, "apiToken": password}
    integrations = testops("GET", "/integration?integrationType=jenkins&size=200")["content"]
    integration = next((item for item in integrations if item["name"] == name), None)
    if integration is None:
        integration = testops("POST", "/integration", {
            "name": name, "type": "jenkins", "settings": {"endpoint": jenkins_url},
            "globalSecret": credentials,
        })
    else:
        testops("PATCH", f"/integration/{integration['id']}", {"globalSecret": credentials})

    integration_id = integration["id"]
    projects = testops("GET", f"/integration/{integration_id}/project?size=200")["content"]
    if all(project["id"] != project_id for project in projects):
        testops("POST", "/integration/project", {"integrationId": integration_id, "projectId": project_id})
    return integration_id


def find_job(testops, project_id):
    jobs = testops("GET", f"/job?projectId={project_id}")["content"]
    return next((item for item in jobs if item.get("externalId") == JOB_NAME), None)


def seed_project(jenkins, testops, project_id, launch_name, integration_id):
    crumb = jenkins("GET", "/crumbIssuer/api/json")
    jenkins("POST", f"/job/{JOB_NAME}/build", {crumb["crumbRequestField"]: crumb["crumb"]})

    def build_result():
        try:
            build = jenkins("GET", f"/job/{JOB_NAME}/lastBuild/api/json")
        except HTTPError as error:
            if error.code == 404:
                return None
            raise
        return build.get("result")

    result = wait_for("первая сборка Jenkins", build_result)
    if result != "SUCCESS":
        raise RuntimeError(f"Первая сборка Jenkins завершилась со статусом {result}.")

    def seed_launch():
        query = urlencode({"projectId": project_id, "size": 100})
        return next((item for item in testops("GET", "/launch?" + query)["content"]
                     if item["name"] == launch_name), None)

    launch_id = wait_for("первая загрузка в TestOps", seed_launch)["id"]

    def complete_results():
        statistics = testops("GET", f"/launch/{launch_id}/statistic")
        total = sum(row["count"] for row in statistics)
        passed = sum(row["count"] for row in statistics if (row.get("status") or "").lower() == "passed")
        return True if total == passed == EXPECTED_RESULTS else None

    wait_for(f"{EXPECTED_RESULTS} успешных результатов в запуске №{launch_id}", complete_results)
    job = find_job(testops, project_id)
    if job is None:
        raise RuntimeError(f"В проекте №{project_id} отсутствует джоба {JOB_NAME}.")
    testops("PATCH", f"/job/{job['id']}", {
        "integrationId": integration_id, "externalId": JOB_NAME, "name": job["name"],
        "canRun": True, "parameters": job.get("parameters") or [],
    })
    testops("POST", f"/launch/{launch_id}/close", {})
    return launch_id


def main():
    testops_url = validate_url(prompt("TESTOPS_URL", "Адрес TestOps из контейнера Jenkins", "http://host.docker.internal:8080"))
    jenkins_url = validate_url(prompt("JENKINS_URL", "Адрес Jenkins с сервера TestOps", "http://localhost:18091"))
    project_id = int(prompt("TESTOPS_PROJECT_ID", "ID демо-проекта"))
    if project_id <= 0:
        raise ValueError("ID демо-проекта должен быть положительным.")
    token = os.environ.get("TESTOPS_TOKEN") or getpass.getpass("API-токен TestOps: ").strip()
    if not token:
        raise ValueError("Укажите API-токен TestOps.")
    local = urlsplit(jenkins_url).hostname in {"localhost", "127.0.0.1", "::1"}
    password = os.environ.get("JENKINS_ADMIN_PASSWORD") or (LOCAL_PASSWORD if local else secrets.token_urlsafe(20))
    launch_name = f"Демо Jenkins {secrets.token_hex(6)}"
    testops_client = build_opener()
    jenkins_client = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
    auth = base64.b64encode(f"{JENKINS_USER}:{password}".encode()).decode()

    def testops(method, path, body=None):
        return request(testops_client, testops_url + "/api",
                       {"Authorization": f"Api-Token {token}", "Content-Type": "application/json"}, method, path, body)

    def jenkins(method, path, headers=None):
        return request(jenkins_client, "http://localhost:8080",
                       {"Authorization": f"Basic {auth}", **(headers or {})}, method, path)

    testops("GET", f"/project/{project_id}")
    if find_job(testops, project_id) is not None:
        raise ValueError(f"В проекте №{project_id} уже есть джоба {JOB_NAME}. Для чистого прогона создайте новый демо-проект.")
    configure_jenkins(Path(os.environ["JENKINS_HOME"]), testops_url, project_id, launch_name)
    env = dict(os.environ, JENKINS_ADMIN_PASSWORD=password, TESTOPS_TOKEN=token)
    process = subprocess.Popen(["/usr/local/bin/jenkins.sh"], env=env)
    try:
        def ready():
            if process.poll() is not None:
                raise RuntimeError("Jenkins завершился до запуска.")
            try:
                result = jenkins("GET", "/whoAmI/api/json")
                if result.get("name") == JENKINS_USER:
                    return True
            except URLError:
                return None

        wait_for("запуск Jenkins", ready)
        integration_id = register_integration(testops, project_id, jenkins_url, password)
        launch_id = seed_project(jenkins, testops, project_id, launch_name, integration_id)
        print(f"Готово. Проект №{project_id}, первая сборка закрыта в запуске №{launch_id}.", flush=True)
        report_url = testops_url.replace("://host.docker.internal", "://localhost", 1) if urlsplit(testops_url).hostname == "host.docker.internal" else testops_url
        print(f"Запуск: {report_url}/launch/{launch_id}", flush=True)
        print(f"Jenkins: {jenkins_url} (логин {JENKINS_USER}, пароль {password})", flush=True)
        return process.wait()
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except HTTPError as error:
        url = urlsplit(error.url)
        sys.exit(f"HTTP {error.code}: {url.netloc}{url.path}")
    except (EOFError, OSError, RuntimeError, ValueError) as error:
        sys.exit(str(error) or "Ввод прерван.")
