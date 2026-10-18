import argparse
import getpass
import sys

from pydantic import ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.provision import provision_runtime_role
from app.db.session import build_engine
from app.modules.identity.service import bootstrap_admin


def main() -> int:
    parser = argparse.ArgumentParser(description="Первоначальная настройка ИТ-элемент [29]")
    sub = parser.add_subparsers(dest="command", required=True)
    admin = sub.add_parser("create-admin", help="Создать первого администратора в пустой users")
    admin.add_argument("--username", required=True)
    admin.add_argument("--display-name", required=True)
    sub.add_parser("provision-db-role", help="Настроить ограниченную runtime роль PostgreSQL")
    args = parser.parse_args()
    engine = None
    try:
        settings = Settings()
        engine = build_engine(settings)
        if args.command == "create-admin":
            if not sys.stdin.isatty():
                raise ValueError("Для безопасного ввода пароля нужен интерактивный терминал (TTY).")
            password = getpass.getpass("Пароль (12–128 символов): ")
            if password != getpass.getpass("Повторите пароль: "):
                raise ValueError("Пароли не совпадают.")
            with Session(engine, expire_on_commit=False) as session:
                bootstrap_admin(session, args.username, args.display_name, password)
            print("Первый администратор создан.")
        else:
            if settings.app_db_password is None:
                raise ValueError("Задайте APP_DB_PASSWORD для ограниченной runtime роли.")
            with engine.begin() as connection:
                provision_runtime_role(
                    connection, settings.app_db_user, settings.app_db_password.get_secret_value()
                )
            print("Runtime роль настроена. Пароль и SQL не выводятся.")
        return 0
    except ValidationError:
        print(
            "Ошибка параметров: проверьте логин, имя, длину пароля и настройки окружения.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except SQLAlchemyError:
        print(
            "Ошибка PostgreSQL. Проверьте подключение, миграции и права оператора.", file=sys.stderr
        )
        return 1
    finally:
        if engine:
            engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
