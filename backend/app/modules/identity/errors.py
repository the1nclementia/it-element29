from fastapi import HTTPException


def fail(status: int, code: str, message: str, headers: dict | None = None):
    raise HTTPException(status, detail={"code": code, "message": message}, headers=headers)
