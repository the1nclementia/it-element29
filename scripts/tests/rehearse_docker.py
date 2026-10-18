"""Opt-in Windows/Docker Desktop rehearsal with synthetic data and separate volumes.

This adapter exercises the deployment state machine and real Linux containers.
It does not validate Ubuntu host permissions, flock, systemd or firewall settings.
"""

import argparse
import json
import os
import secrets
import shutil
import subprocess
import sys
from pathlib import Path

parser = argparse.ArgumentParser(
    description="Репетиция offline deploy в Docker Desktop"
)
parser.add_argument("--run", action="store_true", required=True)
parser.add_argument("--backend-image", default="element29/backend:0.1.0-acceptance")
parser.add_argument("--frontend-image", default="element29/frontend:0.1.0-acceptance")
args = parser.parse_args()
if sys.platform != "win32":
    parser.error("Адаптер предназначен для Windows Docker Desktop")

repo = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(repo / "scripts/deploy"))
from release_lib import DEPLOY_FILES, RELEASE_FILES, verify_release, write_checksums

import deploy

project = "e29-release-test"
existing_containers = deploy.execute(
    ["docker", "ps", "-aq", "--filter", "label=com.docker.compose.project=" + project]
).strip()
existing_volumes = deploy.execute(
    ["docker", "volume", "ls", "--format", "{{.Name}}"]
).splitlines()
if existing_containers or any(
    name in existing_volumes for name in [project + "-postgres", project + "-files"]
):
    raise RuntimeError("Тестовый контур уже существует; сначала проверьте его вручную")

base = repo / (".scratch/release-live-" + secrets.token_hex(3))
base.mkdir(exist_ok=False)
tls = base / "tls"
tls.mkdir()
openssl = shutil.which("openssl") or str(
    Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/usr/bin/openssl.exe"
)
subprocess.run(
    [
        openssl,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "2",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost",
        "-keyout",
        str(tls / "privkey.pem"),
        "-out",
        str(tls / "fullchain.pem"),
    ],
    check=True,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
)
config = base / "test.env"
config.write_text(
    "\n".join(
        [
            "POSTGRES_DB=release_test",
            "POSTGRES_USER=release_owner",
            "POSTGRES_PASSWORD=" + secrets.token_hex(32),
            "APP_DB_USER=release_runtime",
            "APP_DB_PASSWORD=" + secrets.token_hex(32),
            'APP_ORIGINS=["https://localhost:19443"]',
            "HTTPS_BIND=127.0.0.1",
            "HTTPS_PORT=19443",
            "TLS_DIRECTORY=/test/tls",
            "TLS_CA_FILE=/test/tls/fullchain.pem",
        ]
    ),
    encoding="utf-8",
)


class WindowsRehearsal(deploy.Deployment):
    def base_env(self):
        return os.environ.copy()

    def prepare(self, root):
        original = self.config["TLS_DIRECTORY"]
        self.config["TLS_DIRECTORY"] = str(tls)
        try:
            return super().prepare(root)
        finally:
            self.config["TLS_DIRECTORY"] = original

    def compose(self, root, *args, **kwargs):
        manifest = verify_release(root)
        env = (
            self.base_env()
            | self.config
            | {"DATA_PREFIX": self.project, "TLS_DIRECTORY": str(tls)}
        )
        env.update(
            {i["service"].upper() + "_IMAGE": i["ref"] for i in manifest["images"]}
        )
        return deploy.execute(
            [
                "docker",
                "compose",
                "--project-name",
                self.project,
                "--project-directory",
                str(root / "deploy"),
                "--env-file",
                "NUL",
                "-f",
                str(root / "deploy/compose.yaml"),
                "--profile",
                "ops",
                *args,
            ],
            env=env,
            **kwargs,
        )

    def health(self, root):
        deploy.execute(
            [
                "curl.exe",
                "--fail",
                "--silent",
                "--show-error",
                "--noproxy",
                "*",
                "--cacert",
                str(tls / "fullchain.pem"),
                "--resolve",
                "localhost:19443:127.0.0.1",
                "https://localhost:19443/api/v1/health/ready",
            ]
        )


def docker(*args):
    return deploy.execute(["docker", *args])


commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
images = []
for service, source in [
    ("backend", args.backend_image),
    ("frontend", args.frontend_image),
    ("postgres", "postgres:17.11-alpine"),
    ("proxy", "nginx:1.30.6-alpine"),
]:
    ref = "element29/" + service + ":0.1.0-rehearsal"
    docker("tag", source, ref)
    info = json.loads(docker("image", "inspect", ref))[0]
    original = (
        "git:" + commit
        if service in {"backend", "frontend"}
        else source + "@" + info["RepoDigests"][0].split("@")[1]
    )
    images.append(
        {
            "service": service,
            "ref": ref,
            "source_ref": original,
            "id": info["Id"],
            "repo_digests": info.get("RepoDigests", []),
        }
    )

old = base / "old"
new = base / "new"
for version, root in [("0.1.0-rehearsal", old), ("0.1.1-rehearsal", new)]:
    root.mkdir()
    for name in DEPLOY_FILES:
        target = root / name
        target.parent.mkdir(exist_ok=True, parents=True)
        shutil.copyfile(repo / name, target)
    manifest = {
        "format": 1,
        "version": version,
        "git_commit": commit,
        "platform": "linux/amd64",
        "postgres_major": 17,
        "images": images,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    if root == old:
        docker(
            "save", "--output", str(root / "images.tar"), *(i["ref"] for i in images)
        )
    else:
        shutil.copyfile(old / "images.tar", root / "images.tar")
    write_checksums(root, RELEASE_FILES)
    verify_release(root)

state = base / "state"
state.mkdir()
obj = WindowsRehearsal("staging", config, state)
obj.project = project
try:
    obj.install(old)
    obj.compose(
        old,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "release_owner",
        "-d",
        "release_test",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "CREATE TABLE rehearsal_marker(value text); INSERT INTO rehearsal_marker VALUES ('before');",
    )
    obj.compose(
        old,
        "run",
        "--rm",
        "--no-deps",
        "file-ops",
        "python",
        "-c",
        "from pathlib import Path; Path('/app/uploads/check.txt').write_text('before')",
    )
    obj.update(new)
    saved = obj.last_backup
    obj.compose(
        new,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "release_owner",
        "-d",
        "release_test",
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        "UPDATE rehearsal_marker SET value='after';",
    )
    obj.compose(
        new,
        "run",
        "--rm",
        "--no-deps",
        "file-ops",
        "python",
        "-c",
        "from pathlib import Path; Path('/app/uploads/check.txt').write_text('after')",
    )
    obj.restore(old, saved, "RESTORE e29-release-test 0.1.0-rehearsal")
    value = obj.compose(
        old,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "release_owner",
        "-d",
        "release_test",
        "-At",
        "-c",
        "SELECT value FROM rehearsal_marker",
    ).strip()
    file_value = obj.compose(
        old,
        "run",
        "--rm",
        "--no-deps",
        "file-ops",
        "python",
        "-c",
        "from pathlib import Path; print(Path('/app/uploads/check.txt').read_text())",
    ).strip()
    assert value == file_value == "before", (value, file_value)
    assert obj.current() == old
    assert not (state / "pending.json").exists()
    print(
        "PASS: real Docker install -> update + verified DB/files backup -> explicit restore -> HTTPS readiness; DB/files restored."
    )
finally:
    obj.compose(old, "down", "--remove-orphans")
    for name in ["e29-release-test-postgres", "e29-release-test-files"]:
        if name in docker("volume", "ls", "--format", "{{.Name}}").splitlines():
            docker("volume", "rm", name)
