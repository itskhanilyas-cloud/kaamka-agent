"""Who is calling?

In Azure, Container Apps built-in authentication (Microsoft Entra ID) sits in
front of the app and injects X-MS-CLIENT-PRINCIPAL-NAME after a successful
sign-in; the header cannot be set by the browser because the platform strips
it from incoming requests. Locally, KA_DEV_AUTH_BYPASS signs you in as the
owner (refused in production by Settings.validate_for_runtime).
"""
from fastapi import Depends, HTTPException, Request, status

from .config import Settings, get_settings

PRINCIPAL_HEADER = "x-ms-client-principal-name"


def current_user(request: Request, settings: Settings = Depends(get_settings)) -> str:
    if settings.dev_auth_bypass and settings.app_env != "production":
        return settings.owner_email
    user = request.headers.get(PRINCIPAL_HEADER)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sign-in required")
    return user.lower()


def require_owner(user: str = Depends(current_user), settings: Settings = Depends(get_settings)) -> str:
    if user != settings.owner_email.lower():
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            f"Signed in as {user}, which is not the owner account set in KA_OWNER_EMAIL.")
    return user
