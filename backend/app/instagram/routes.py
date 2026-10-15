from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse, Response
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..db import get_db
from ..models import Media, OAuthState, utcnow
from ..security import require_owner
from ..services import audit
from . import service
from .client import InstagramClient, InstagramError

router = APIRouter()
STATE_TTL = timedelta(minutes=15)


def client_for(settings: Settings) -> InstagramClient:
    if not settings.instagram_ready:
        raise HTTPException(503, "Instagram is not configured yet (app ID, secret, encryption key, public URL)")
    return InstagramClient(settings.instagram_app_id, settings.instagram_app_secret.get_secret_value(),
                           settings.public_base_url.rstrip("/") + "/instagram/callback")


@router.get("/api/instagram/status")
def status(db: Session = Depends(get_db), _: str = Depends(require_owner), settings: Settings = Depends(get_settings)):
    acct = service.current_account(db)
    return {"configured": settings.instagram_ready,
            "connected": bool(acct and acct.token_enc),
            "username": acct.username if acct else None,
            "account_type": acct.account_type if acct else None,
            "token_expires_at": acct.token_expires_at if acct else None}


@router.get("/instagram/connect")
def connect(db: Session = Depends(get_db), user: str = Depends(require_owner), settings: Settings = Depends(get_settings)):
    client = client_for(settings)
    state = service.new_state()
    db.add(OAuthState(state=state, created_by=user))
    audit.record(db, user, "instagram_connect_started", None)
    db.commit()
    return RedirectResponse(client.authorize_url(state), status_code=302)


@router.get("/instagram/callback")
def callback(code: str | None = None, state: str | None = None, error: str | None = None,
             error_description: str | None = None, db: Session = Depends(get_db),
             user: str = Depends(require_owner), settings: Settings = Depends(get_settings)):
    if error:
        audit.record(db, user, "instagram_connect_declined", None, error=error)
        db.commit()
        return RedirectResponse("/#/settings?ig=declined", status_code=302)
    row = db.get(OAuthState, state or "")
    created = row.created_at if row and row.created_at.tzinfo else (row.created_at.replace(tzinfo=utcnow().tzinfo) if row else None)
    if not row or row.created_by != user or utcnow() - created > STATE_TTL:
        raise HTTPException(400, "This connect link has expired or was not started by you. Please try again.")
    db.delete(row)
    if not code:
        raise HTTPException(400, "Instagram did not return an authorization code")
    try:
        service.save_connection(db, client_for(settings), settings.token_encryption_key.get_secret_value(), code, user)
    except InstagramError as e:
        audit.record(db, user, "instagram_connect_failed", None, error=str(e))
        db.commit()
        raise HTTPException(502, str(e))
    db.commit()
    return RedirectResponse("/#/settings?ig=connected", status_code=302)


@router.post("/api/instagram/disconnect")
def disconnect(db: Session = Depends(get_db), user: str = Depends(require_owner)):
    service.disconnect(db, user)
    db.commit()
    return {"connected": False}


# Public, unauthenticated, but only with a valid short-lived signature for one image.
@router.get("/public/media/{media_id}.jpg")
def public_media(media_id: str, exp: int = Query(...), sig: str = Query(..., max_length=128),
                 db: Session = Depends(get_db), settings: Settings = Depends(get_settings)):
    if not settings.token_encryption_key or not service.verify_media(
            settings.token_encryption_key.get_secret_value(), media_id, exp, sig):
        raise HTTPException(404, "not found")
    m = db.get(Media, media_id)
    if not m:
        raise HTTPException(404, "not found")
    return Response(m.data, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=600"})
