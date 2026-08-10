from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.config import settings

security = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role


def get_current_user_optional(
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> CurrentUser | None:
    if credentials is None or not credentials.credentials:
        return None

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = payload.get("sub")
        username = payload.get("username")
        role = payload.get("role")

        if not user_id or not username or not role:
            return None

        return CurrentUser(
            user_id=str(user_id),
            username=str(username),
            role=str(role),
        )
    except JWTError:
        return None


def get_current_user(
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> CurrentUser:
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials were not provided or are invalid.",
        )
    return current_user
