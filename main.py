from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from database import engine, SessionLocal
from models.url import URL, Base
from models.user import User
from services.url_service import generate_short_code
from passlib.context import CryptContext
from models.admin import Admin
from starlette.middleware.sessions import SessionMiddleware
from models.click import Click
from datetime import datetime, timedelta, timezone
from io import BytesIO

import base64
import os
import validators
import qrcode


app = FastAPI()

app.add_middleware(
    SessionMiddleware,
    secret_key="change-this-secret-key"
)

# ==========================================
# PASSWORD HASHING
# ==========================================

pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto"
)




# ==========================================
# TEMPLATES
# ==========================================

templates = Jinja2Templates(directory="templates")


# ==========================================
# STATIC FILES
# ==========================================

app.mount(
    "/static",
    StaticFiles(directory="static"),
    name="static"
)


# ==========================================
# CREATE DATABASE TABLES
# ==========================================

Base.metadata.create_all(bind=engine)


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# AD INTERSTITIAL SETTINGS
# ==========================================

# ==========================================
# PUBLIC BASE URL
# ==========================================

# Public address the short links are built on.
# request.base_url only echoes the host the
# browser used, which gives http://127.0.0.1:8000
# in local dev - a link nobody else can open.
# Set PUBLIC_BASE_URL in the environment once
# deployed, e.g. https://sho.rt

PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL")


def build_short_url(
    request: Request,
    short_code: str
) -> str:

    base = PUBLIC_BASE_URL or str(request.base_url)

    return f"{base.rstrip('/')}/{short_code}"


AD_COUNTDOWN_SECONDS = 5


# ==========================================
# ANTI-FRAUD SETTINGS
# ==========================================

# Same IP clicking the same short link again
# within this window doesn't count as a new
# monetized click.

ANTI_FRAUD_WINDOW_HOURS = 24


# ==========================================
# GET REAL CLIENT IP (reverse-proxy aware)
# ==========================================

def get_client_ip(request: Request) -> str | None:

    # If the app sits behind a reverse proxy
    # (nginx, Render, Railway, Cloudflare...),
    # request.client.host is the proxy's IP,
    # not the visitor's. The real IP is the
    # first one in X-Forwarded-For.

    forwarded_for = request.headers.get(
        "x-forwarded-for"
    )

    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    if request.client:
        return request.client.host

    return None


# ==========================================
# ANTI-FRAUD: HAS THIS IP ALREADY CLICKED
# THIS LINK IN THE LAST 24H?
# ==========================================

def is_duplicate_click(
    db: Session,
    url_id: int,
    ip_address: str | None
) -> bool:

    # No IP captured at all -> can't verify
    # uniqueness, so it's treated as unsafe
    # to monetize (see redirect_url below).

    if not ip_address:
        return True

    window_start = (
        datetime.now(timezone.utc)
        - timedelta(hours=ANTI_FRAUD_WINDOW_HOURS)
    )

    existing = db.query(Click).filter(
        Click.url_id == url_id,
        Click.ip_address == ip_address,
        Click.clicked_at >= window_start
    ).first()

    return existing is not None


# ==========================================
# OBFUSCATE DESTINATION URL FOR THE
# INTERSTITIAL PAGE SOURCE
# ==========================================

# Not real encryption - the goal is just to
# stop a casual "View Source" from revealing
# the destination in plain text before the
# countdown finishes. The URL is reversed
# then base64-encoded; the browser reverses
# the operation client-side (see ad countdown
# JS in index.html).

def obfuscate_url(url: str) -> str:

    # Reverse the UTF-8 BYTES, not the characters.
    # The browser undoes the operation at byte level
    # too, so multi-byte characters (accents, IDN,
    # emoji) survive the round trip intact.

    reversed_bytes = url.encode("utf-8")[::-1]

    return base64.b64encode(
        reversed_bytes
    ).decode("ascii")


# ==========================================
# CREATE SHORT URL
# ==========================================

def create_short_url(
    original_url: str,
    db: Session
) -> URL:

    # 1. Validate URL
    if not validators.url(original_url):
        raise HTTPException(
            status_code=400,
            detail="Invalid URL"
        )

    # 2. Check if URL already exists
    existing_url = db.query(URL).filter(
        URL.original_url == original_url
    ).first()

    if existing_url:
        return existing_url

    # 3. Create URL object
    new_url = URL(
        original_url=original_url,
        short_code="TEMP"
    )

    db.add(new_url)

    # Get generated ID
    db.flush()

    # 4. Generate Base62 short code
    new_url.short_code = generate_short_code(
        new_url.id
    )

    # 5. Save
    db.commit()
    db.refresh(new_url)

    return new_url


# ==========================================
# CURRENT USER HELPER (public accounts,
# separate from the Admin login)
# ==========================================

def get_current_user(
    request: Request,
    db: Session
) -> User | None:

    user_id = request.session.get("user_id")

    if not user_id:
        return None

    return db.query(User).filter(
        User.id == user_id
    ).first()


# ==========================================
# JSON API
# ==========================================

@app.post("/api/shorten")
def shorten_url(
    original_url: str,
    db: Session = Depends(get_db)
):

    new_url = create_short_url(
        original_url,
        db
    )

    return {
        "short_code": new_url.short_code
    }


# ==========================================
# HTML SHORTEN FORM
# ==========================================

@app.post("/shorten", response_class=HTMLResponse)
def shorten_form(
    request: Request,
    original_url: str = Form(...),
    db: Session = Depends(get_db)
):

    new_url = create_short_url(
        original_url,
        db
    )

    short_url = build_short_url(
        request,
        new_url.short_code
    )

    user = get_current_user(request, db)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "short_url": short_url,
            "original_url": new_url.original_url,
            "click_count": 0,
            "url_id": new_url.id,
            "user": user
        }
    )


# ==========================================
# HOME PAGE
# ==========================================

@app.get("/", response_class=HTMLResponse)
def home(
    request: Request,
    db: Session = Depends(get_db)
):

    user = get_current_user(request, db)

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "user": user
        }
    )


# ==========================================
# LOGIN PAGE
# ==========================================

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):

    return templates.TemplateResponse(
        request,
        "login.html"
    )

@app.post("/login", response_class=HTMLResponse)
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    # 1. Tentative de connexion admin
    admin = db.query(Admin).filter(
        Admin.email == email
    ).first()

    if admin and pwd_context.verify(
        password,
        admin.password_hash
    ):

        request.session["admin_id"] = admin.id
        request.session["admin_email"] = admin.email

        return RedirectResponse(
            url="/admin",
            status_code=303
        )

    # 2. Tentative de connexion utilisateur public
    user = db.query(User).filter(
        User.email == email
    ).first()

    if user and pwd_context.verify(
        password,
        user.password_hash
    ):

        request.session["user_id"] = user.id
        request.session["user_email"] = user.email

        return RedirectResponse(
            url="/",
            status_code=303
        )

    # 3. Aucune correspondance
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "error": "Email ou mot de passe incorrect."
        }
    )

@app.get("/admin", response_class=HTMLResponse)
def admin_page(
    request: Request,
    db: Session = Depends(get_db)
):

    # Vérifier si l'admin est connecté
    admin_id = request.session.get("admin_id")

    if not admin_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Récupérer l'admin
    admin = db.query(Admin).filter(
        Admin.id == admin_id
    ).first()

    if not admin:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Récupérer toutes les URLs
    urls = db.query(URL).order_by(
        URL.id.desc()
    ).all()

    # Ajouter le nombre de clics
    url_data = []

    for url in urls:

        click_count = db.query(Click).filter(
            Click.url_id == url.id
        ).count()

        url_data.append({
            "id": url.id,
            "original_url": url.original_url,
            "short_code": url.short_code,
            "created_at": url.created_at,
            "click_count": click_count
        })

    # ==========================================
    # STATS DASHBOARD NUMBERS
    # ==========================================

    total_urls = len(url_data)

    total_clicks = db.query(Click).count()

    monetized_clicks = db.query(Click).filter(
        Click.is_monetized == True
    ).count()

    blocked_clicks = total_clicks - monetized_clicks

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "admin": admin,
            "urls": url_data,
            "total_urls": total_urls,
            "total_clicks": total_clicks,
            "monetized_clicks": monetized_clicks,
            "blocked_clicks": blocked_clicks
        }
    )
# ==========================================
# SIGN IN PAGE (public account creation)
# ==========================================

@app.get("/signin", response_class=HTMLResponse)
def signin_page(request: Request):

    return templates.TemplateResponse(
        request,
        "signin.html"
    )

@app.post("/signin", response_class=HTMLResponse)
def signin(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    db: Session = Depends(get_db)
):

    # 1. Vérifier que les 2 mots de passe correspondent
    if password != password_confirm:

        return templates.TemplateResponse(
            request,
            "signin.html",
            {
                "error": "Les mots de passe ne correspondent pas."
            }
        )

    # 2. Vérifier que l'email n'est pas déjà utilisé
    existing_user = db.query(User).filter(
        User.email == email
    ).first()

    if existing_user:

        return templates.TemplateResponse(
            request,
            "signin.html",
            {
                "error": "Un compte existe déjà avec cet email."
            }
        )

    # 3. Créer le compte
    new_user = User(
        email=email,
        password_hash=pwd_context.hash(password)
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 4. Connecter automatiquement l'utilisateur
    request.session["user_id"] = new_user.id
    request.session["user_email"] = new_user.email

    return RedirectResponse(
        url="/",
        status_code=303
    )


# ==========================================
# LOGOUT (public account)
# ==========================================

@app.get("/logout")
def logout(request: Request):

    request.session.clear()

    return RedirectResponse(
        url="/",
        status_code=303
    )


@app.get("/api/clicks/{url_id}")
def get_click_count(
    url_id: int,
    db: Session = Depends(get_db)
):

    url = db.query(URL).filter(
        URL.id == url_id
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )

    click_count = db.query(Click).filter(
        Click.url_id == url_id
    ).count()

    return {
        "url_id": url_id,
        "click_count": click_count
    }


# ==========================================
# QR CODE (only for logged-in public users)
# ==========================================

@app.get("/qr/{url_id}")
def get_qr_code(
    url_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    # 1. L'utilisateur doit avoir un compte
    user = get_current_user(request, db)

    if not user:
        raise HTTPException(
            status_code=401,
            detail="Connexion requise pour générer un QR Code"
        )

    # 2. Récupérer l'URL
    url = db.query(URL).filter(
        URL.id == url_id
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )

    short_url = build_short_url(
        request,
        url.short_code
    )

    # 3. Générer le QR code en PNG en mémoire
    qr_img = qrcode.make(short_url)

    buffer = BytesIO()

    qr_img.save(buffer, format="PNG")

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="image/png"
    )


@app.get(
    "/counter/{url_id}",
    response_class=HTMLResponse
)
def counter_page(
    url_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    # Chercher l'URL
    url = db.query(URL).filter(
        URL.id == url_id
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )

    # Compter les clics
    click_count = db.query(Click).filter(
        Click.url_id == url_id
    ).count()

    return templates.TemplateResponse(
        request,
        "counter.html",
        {
            "url": url,
            "click_count": click_count
        }
    )

@app.get(
    "/admin/counter/{url_id}",
    response_class=HTMLResponse
)
def admin_counter_page(
    url_id: int,
    request: Request,
    db: Session = Depends(get_db)
):

    # Vérifier si l'admin est connecté
    # (avant, cette route était accessible à
    # n'importe qui connaissant un url_id -
    # corrigé ici pour exiger une session admin)

    admin_id = request.session.get("admin_id")

    if not admin_id:
        return RedirectResponse(
            url="/login",
            status_code=303
        )

    admin = db.query(Admin).filter(
        Admin.id == admin_id
    ).first()

    if not admin:
        request.session.clear()

        return RedirectResponse(
            url="/login",
            status_code=303
        )

    # Chercher l'URL
    url = db.query(URL).filter(
        URL.id == url_id
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )


    # Compter les clics
    click_count = db.query(Click).filter(
        Click.url_id == url_id
    ).count()


    return templates.TemplateResponse(
        request,
        "counter.html",
        {
            "url": url,
            "click_count": click_count
        }
    )

# ==========================================
# REDIRECT SHORT URL (via ad interstitial)
# ==========================================
#
# NOTE: this catch-all route must stay LAST
# among GET routes with a single path segment
# (like /qr/{url_id}, /login, /signin...),
# otherwise it would swallow them. FastAPI
# matches routes in declaration order.

@app.get("/{short_code}", response_class=HTMLResponse)
def redirect_url(
    short_code: str,
    request: Request,
    db: Session = Depends(get_db)
):

    # 1. Find the URL in the database
    url = db.query(URL).filter(
        URL.short_code == short_code
    ).first()

    if not url:
        raise HTTPException(
            status_code=404,
            detail="URL not found"
        )

    # 2. Get visitor information (proxy-aware IP)
    ip_address = get_client_ip(request)

    user_agent = request.headers.get("user-agent")

    # 3. Anti-fraud: same IP already clicked this
    #    exact link in the last 24h -> not monetized
    duplicate = is_duplicate_click(
        db,
        url.id,
        ip_address
    )


    # 4. Create a new click (this visit passes through the ad)
    try:

        click = Click(
            url_id=url.id,
            ip_address=ip_address,
            user_agent=user_agent,
            is_monetized=not duplicate
        )

        # 5. Save the click in PostgreSQL
        db.add(click)
        db.commit()

    except Exception as e:
        db.rollback()
        print(f"Erreur lors de l'enregistrement du clic : {e}")

    # 6. Show the ad interstitial on top of index.html.
    #    Destination is obfuscated - it's decoded and
    #    used for redirect client-side after the
    #    countdown finishes.
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "show_ad": True,
            "destination_encoded": obfuscate_url(url.original_url),
            "countdown": AD_COUNTDOWN_SECONDS,
            "page_url": build_short_url(request, short_code)
        }
    )