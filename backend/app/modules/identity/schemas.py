import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

RoleCode = Literal["administrator", "it_specialist", "storekeeper", "manager"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


def normalized_username(value: str) -> str:
    value = value.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{2,63}", value):
        raise ValueError("Логин: 3–64 латинских буквы, цифры, точка, дефис или подчёркивание")
    return value


def valid_password(value: SecretStr) -> SecretStr:
    if not 12 <= len(value.get_secret_value()) <= 128 or not value.get_secret_value().strip():
        raise ValueError("Пароль должен содержать от 12 до 128 символов")
    return value


class LoginInput(InputModel):
    username: str = Field(min_length=1, max_length=128)
    password: SecretStr = Field(max_length=128)


class CreateUserInput(InputModel):
    username: str
    display_name: str = Field(min_length=1, max_length=160)
    role: RoleCode
    password: SecretStr

    _username = field_validator("username")(normalized_username)
    _password = field_validator("password")(valid_password)

    @field_validator("display_name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Укажите имя пользователя")
        return value.strip()


class UpdateUserInput(InputModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=160)
    role: RoleCode | None = None
    is_active: bool | None = None

    @field_validator("display_name", "role", "is_active", mode="before")
    @classmethod
    def explicit_null_forbidden(cls, value):
        if value is None:
            raise ValueError("Значение не может быть null")
        if isinstance(value, str):
            value = value.strip()
            if not value:
                raise ValueError("Значение не может быть пустым")
        return value


class ResetPasswordInput(InputModel):
    new_password: SecretStr
    _password = field_validator("new_password")(valid_password)


class ChangePasswordInput(ResetPasswordInput):
    current_password: SecretStr = Field(max_length=128)


class UserResponse(BaseModel):
    id: uuid.UUID
    username: str
    display_name: str
    role: RoleCode
    role_name: str
    permissions: list[str]
    is_active: bool
    must_change_password: bool
    created_at: datetime
