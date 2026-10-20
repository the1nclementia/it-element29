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

run_id = secrets.token_hex(5)
project = "e29-release-test-" + run_id
restore_project = "e29-restore-test-" + run_id
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

base = repo / (".scratch/release-live-" + run_id)
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
restore_config = base / "restore.env"
restore_config.write_text(
    config.read_text(encoding="utf-8")
    .replace("release_test", "restore_test")
    .replace("19443", "19444"),
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
        port = self.config["HTTPS_PORT"]
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
                f"localhost:{port}:127.0.0.1",
                f"https://localhost:{port}/api/v1/health/ready",
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
    ref = "element29/" + service + ":0.1.0-rehearsal-" + run_id
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
restore_state = base / "restore-state"
restore_state.mkdir()
restored = WindowsRehearsal("staging", restore_config, restore_state)
restored.project = restore_project

seed_code = """
import secrets, uuid
from datetime import UTC, datetime, timedelta, date
from io import BytesIO
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import build_engine
from app.modules.directory import models as directory_models
from app.modules.files.service import add_photo
from app.modules.identity.models import User, AuthSession
from app.modules.identity.service import bootstrap_admin
from app.modules.inventory.models import Manufacturer, InventoryCategory, InventoryItem
from app.modules.inventory.stock_schemas import ReceiptInput
from app.modules.inventory.stock_service import conduct
from app.modules.inventory.draft_schemas import DraftCreate
from app.modules.inventory.draft_service import create as create_draft
settings = Settings()
engine = build_engine(settings)
with Session(engine) as session:
    user_id = bootstrap_admin(session, 'rehearsal', 'Synthetic operator', secrets.token_urlsafe(32) + 'aA1!').id
    actor = session.get(User, user_id)
    manufacturer = Manufacturer(name='Synthetic manufacturer', name_key='synthetic manufacturer')
    session.add(manufacturer)
    session.flush()
    category = session.scalar(select(InventoryCategory).where(InventoryCategory.code == 'cartridges'))
    item = InventoryItem(internal_code='REHEARSAL-1', model='Synthetic model', category_id=category.id, manufacturer_id=manufacturer.id)
    session.add(item)
    token = secrets.token_hex(32)
    session.add(AuthSession(token_hash=token, user_id=user_id, expires_at=datetime.now(UTC)+timedelta(hours=2)))
    session.commit()
    conduct(session, actor, token, uuid.uuid4(), ReceiptInput(document_date=date.today(), receipt_purpose='opening_balance', items=[{'inventory_item_id': item.id, 'quantity': 10}]))
    output = BytesIO()
    Image.new('RGB', (12, 7), 'blue').save(output, format='PNG')
    add_photo(session, settings, actor, token, item.id, output.getvalue(), 'image/png')
    create_draft(session, actor, token, DraftCreate(document_type='receipt', payload={'items': [{'inventory_item_id': str(item.id), 'quantity': 3}]}))
engine.dispose()
"""

snapshot_code = """
import hashlib, json
from sqlalchemy import MetaData, select
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.db.session import build_engine
from app.modules.directory import models as directory_models
from app.modules.identity import models as identity_models
from app.modules.inventory import models as inventory_models
from app.modules.files import models as file_models
settings = Settings()
engine = build_engine(settings)
snapshot = {}
metadata = MetaData()
# The owner-only marker is checked separately; all application tables are read
# through the restricted runtime role, including the Alembic revision.
metadata.reflect(bind=engine, only=lambda name, _: name != 'rehearsal_marker')
with Session(engine) as session:
    for table in metadata.sorted_tables:
        rows = sorted(json.dumps(dict(row), sort_keys=True, default=str) for row in session.execute(select(table)).mappings())
        snapshot[table.name] = {'rows': len(rows), 'sha256': hashlib.sha256(json.dumps(rows).encode()).hexdigest()}
    for file in session.scalars(select(file_models.FileAttachment)):
        data = (settings.uploads_dir / file.storage_key).read_bytes()
        assert hashlib.sha256(data).hexdigest() == file.sha256
        assert len(data) == file.size
        snapshot['file:' + str(file.id)] = file.sha256
engine.dispose()
print(json.dumps(snapshot, sort_keys=True))
"""


def snapshot(operation, release):
    return json.loads(
        operation.compose(
            release,
            "run",
            "--rm",
            "--no-deps",
            "runtime-ops",
            "python",
            "-c",
            snapshot_code,
        )
    )


try:
    obj.install(old)
    obj.compose(
        old, "run", "--rm", "--no-deps", "runtime-ops", "python", "-c", seed_code
    )
    before = snapshot(obj, old)
    assert before["inventory_documents"]["rows"] == 1
    assert before["inventory_movements"]["rows"] == 1
    assert before["file_attachments"]["rows"] == 1
    assert before["inventory_drafts"]["rows"] == 1
    obj.compose(old, "up", "-d", "--no-deps", "--force-recreate", "--wait", "backend")
    assert snapshot(obj, old) == before
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
    restored.restore_new(old, saved, f"RESTORE-NEW {restore_project} 0.1.0-rehearsal")
    assert snapshot(restored, old) == before
    value = restored.compose(
        old,
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        "release_owner",
        "-d",
        "restore_test",
        "-At",
        "-c",
        "SELECT value FROM rehearsal_marker",
    ).strip()
    file_value = restored.compose(
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
    source_value = obj.compose(
        new,
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
    assert source_value == "after"
    assert obj.current() == new and restored.current() == old
    assert not (restore_state / "pending.json").exists()
    (base / "verification.json").write_text(
        json.dumps(
            {
                "source_project": project,
                "target_project": restore_project,
                "snapshot": before,
                "backup": str(saved),
                "source_preserved": True,
                "photo_survived_recreate": True,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "PASS: install, photo recreate, update/backup, restore-new, runtime data/file hashes and HTTPS readiness. Source unchanged."
    )
finally:
    print(
        f"Сохранены контейнеры/volumes {project} и {restore_project}; артефакты: {base}"
    )
