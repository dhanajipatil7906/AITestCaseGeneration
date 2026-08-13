from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from app.config import settings


def _decode_token(token: str | None) -> CurrentUser | None:
    if not token:
        return None

    try:
        payload = jwt.decode(
            token,
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

security = HTTPBearer(auto_error=False)


class CurrentUser:
    def __init__(self, user_id: str, username: str, role: str):
        self.user_id = user_id
        self.username = username
        self.role = role


def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Security(security),
) -> CurrentUser | None:
    token = None

    if credentials is not None and credentials.credentials:
        token = credentials.credentials

    if token is None:
        token = request.query_params.get("token")

    if token is None:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]

    if token is None:
        token = request.cookies.get("access_token")

    return _decode_token(token)


def get_current_user(
    current_user: CurrentUser | None = Depends(get_current_user_optional),
) -> CurrentUser:
    if current_user is None:
        raise HTTPException(
            status_code=401,
            detail="Authentication credentials were not provided or are invalid.",
        )
    return current_user
