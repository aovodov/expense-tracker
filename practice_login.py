"""Interactive sign-in for uploading to the TestOps practice project."""

import getpass
import json
import re
import sys
import warnings
from contextlib import contextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import (
    HTTPCookieProcessor,
    HTTPRedirectHandler,
    ProxyHandler,
    Request,
    build_opener,
)

DEFAULT_ENDPOINT = "http://localhost:8080"
PRACTICE_PROJECT = "Практикум: учёт расходов"


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def find_practice_project(request) -> int:
    candidates = {}
    page = 0
    while True:
        query = urlencode({"query": "Практикум", "write": "true", "page": page})
        result = request("/api/project/suggest?" + query)
        for project in result["content"]:
            if re.fullmatch(re.escape(PRACTICE_PROJECT) + r"(?: \d+)?", project["name"]):
                candidates[project["id"]] = project["name"]
        page += 1
        if page >= result["totalPages"]:
            break
    if not candidates:
        raise RuntimeError(f"Проект «{PRACTICE_PROJECT}» не найден.")
    if len(candidates) == 1:
        return next(iter(candidates))
    for project_id, name in candidates.items():
        print(f"{project_id}  {name}")
    while True:
        selection = input("Введите ID проекта из списка: ").strip()
        if selection.isascii() and selection.isdecimal() and int(selection) in candidates:
            return int(selection)


@contextmanager
def practice_credentials(endpoint: str, project_id: int | None):
    url = urlsplit(endpoint)
    local_http = url.scheme == "http" and url.hostname in {"localhost", "127.0.0.1", "::1"}
    if (
        (url.scheme != "https" and not local_http)
        or not url.hostname
        or url.username is not None
        or url.query
        or url.fragment
    ):
        raise RuntimeError("Укажите адрес TestOps с HTTPS или локальный адрес с HTTP.")
    if not sys.stdin.isatty():
        raise RuntimeError("Откройте терминал для входа в ТестОпс.")

    # Browsers accept Secure cookies on loopback HTTP. Match that only for this client.
    protocols = ("https", "http") if local_http else ("https",)
    cookies = CookieJar(DefaultCookiePolicy(secure_protocols=protocols))
    proxy = ProxyHandler({}) if local_http else ProxyHandler()
    client = build_opener(proxy, HTTPCookieProcessor(cookies), NoRedirects())

    def request(path, *, method="GET", data=None, headers=None):
        message = Request(endpoint + path, method=method, data=data, headers=headers or {})
        try:
            with client.open(message, timeout=15) as response:
                body = response.read()
                return json.loads(body) if body else None
        except HTTPError as error:
            raise RuntimeError(f"ТестОпс ответил HTTP {error.code} на {method} {path.split('?')[0]}.") from None
        except (URLError, TimeoutError, ValueError) as error:
            raise RuntimeError(f"Не удалось выполнить {method} {path.split('?')[0]} в ТестОпс.") from error

    print(f"ТестОпс: {endpoint}")
    username = input("Логин: ").strip()
    with warnings.catch_warnings():
        warnings.simplefilter("error", getpass.GetPassWarning)
        try:
            password = getpass.getpass("Пароль: ")
        except getpass.GetPassWarning:
            raise RuntimeError("Откройте терминал, который поддерживает скрытый ввод пароля.") from None
    request(
        "/api/login/system",
        method="POST",
        data=urlencode({"username": username, "password": password}).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    request("/api/account/me")
    csrf = next((cookie.value for cookie in cookies if cookie.name == "XSRF-TOKEN"), None)
    if not csrf:
        raise RuntimeError("ТестОпс не завершил вход. Проверьте настройки входа на инстансе.")
    if project_id is None:
        project_id = find_practice_project(request)

    headers = {"Content-Type": "application/json", "X-XSRF-TOKEN": csrf}
    token = request(
        "/api/token",
        method="POST",
        data=json.dumps({"name": "expense-tracker-practice"}).encode(),
        headers=headers,
    )
    try:
        yield endpoint, project_id, token["token"]
    finally:
        try:
            request(f"/api/token/{token['id']}", method="DELETE", headers=headers)
        except RuntimeError as error:
            print(f"Не удалось отозвать временный API-токен {token['id']}. {error}", file=sys.stderr)
