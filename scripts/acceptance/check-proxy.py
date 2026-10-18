"""Container regression: real client IP, spoofed XFF and private query logging.

Only for a disposable e29-acceptance* Compose project, never the user environment.
Requires running backend, frontend, proxy and postgres plus a backend runtime image.
"""

import argparse
import json
import subprocess
import uuid


def output(command):
    return subprocess.check_output(command, text=True, encoding="utf-8").strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--env-file", required=True)
    parser.add_argument("--compose", action="append", required=True)
    parser.add_argument("--backend-image", required=True)
    parser.add_argument("--origin", required=True)
    args = parser.parse_args()
    if not args.project.startswith("e29-acceptance"):
        parser.error(
            "Нужен отдельный проект e29-acceptance*, содержащий только тестовые данные."
        )
    compose = ["docker", "compose", "-p", args.project, "--env-file", args.env_file]
    for path in args.compose:
        compose += ["-f", path]
    query = """import json
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import build_engine
from app.modules.identity.models import AuthRateLimit
with Session(build_engine(Settings())) as s:
 print(json.dumps(dict(s.execute(select(AuthRateLimit.key_hash,AuthRateLimit.attempts)).all())))
"""
    before = json.loads(
        output(compose + ["exec", "-T", "backend", "python", "-c", query])
    )
    marker = "privacy_probe_" + uuid.uuid4().hex
    client = """import hashlib,http.cookiejar,json,socket,sys,urllib.request,urllib.error
opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
csrf=json.load(opener.open('http://proxy/api/v1/auth/csrf'))['csrf_token']
request=urllib.request.Request('http://proxy/api/v1/auth/login',
 data=json.dumps({'username':sys.argv[2], 'password':'invalid-test-password'}).encode(),
 headers={'Origin':sys.argv[1], 'X-CSRF-Token':csrf, 'Content-Type':'application/json',
 'X-Forwarded-For':'198.51.100.99'})
try: opener.open(request)
except urllib.error.HTTPError as error: assert error.code==401
else: raise AssertionError('Unknown test user authenticated')
ip=socket.gethostbyname(socket.gethostname())
print(hashlib.sha256(('ip:'+ip).encode()).hexdigest())
opener.open('http://proxy/api/v1/health/live?'+sys.argv[2])
"""
    key = output(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            args.project + "_edge",
            args.backend_image,
            "python",
            "-c",
            client,
            args.origin,
            marker,
        ]
    )
    after = json.loads(
        output(compose + ["exec", "-T", "backend", "python", "-c", query])
    )
    assert after.get(key) == before.get(key, 0) + 1, (
        "Лимит привязан не к адресу клиента"
    )
    logs = output(compose + ["logs", "--no-color", "backend", "proxy", "frontend"])
    assert marker not in logs, "Параметры URL попали в журнал"
    print(
        "PASS: адрес клиента, защита от подмены XFF, отсутствие query string в логах."
    )


if __name__ == "__main__":
    main()
