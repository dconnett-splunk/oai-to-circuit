import secrets
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from oai_to_circuit.config import BridgeConfig


def build_admin_guard(config: BridgeConfig):
    security = HTTPBasic(auto_error=False)

    def require_admin(credentials: Optional[HTTPBasicCredentials] = Depends(security)) -> None:
        if not config.admin_password:
            return

        expected_username = config.admin_username or "admin"
        if credentials is None:
            raise HTTPException(
                status_code=401,
                detail="Admin authentication required",
                headers={"WWW-Authenticate": 'Basic realm="admin"'},
            )

        username_ok = secrets.compare_digest(credentials.username, expected_username)
        password_ok = secrets.compare_digest(credentials.password, config.admin_password)
        if username_ok and password_ok:
            return

        raise HTTPException(
            status_code=401,
            detail="Invalid admin credentials",
            headers={"WWW-Authenticate": 'Basic realm="admin"'},
        )

    return require_admin
