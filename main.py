from fastapi import FastAPI, Depends, HTTPException, Request, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from database import engine, SessionLocal
from models.url import URL, Base
from services.url_service import generate_short_code
from passlib.context import CryptContext
from models.admin import Admin
from starlette.middleware.sessions import SessionMiddleware
from models.click import Click

import validators


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

    short_url = (
        f"{request.base_url}"
        f"{new_url.short_code}"
    )

    return templates.TemplateResponse(
    request,
    "index.html",
    {
        "short_url": short_url,
        "click_count": 0,
        "url_id": new_url.id
    }
)


# ==========================================
# HOME PAGE
# ==========================================

@app.get("/", response_class=HTMLResponse)
def home(request: Request):

    return templates.TemplateResponse(
        request,
        "index.html"
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
    # Chercher l'admin dans PostgreSQL
    admin = db.query(Admin).filter(
        Admin.email == email
    ).first()

    # Admin inexistant
    if not admin:
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Email ou mot de passe incorrect."
            }
        )

    # Vérifier le mot de passe avec bcrypt
    if not pwd_context.verify(
        password,
        admin.password_hash
    ):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "error": "Email ou mot de passe incorrect."
            }
        )

    # Connexion réussie
    request.session["admin_id"] = admin.id
    request.session["admin_email"] = admin.email

    return RedirectResponse(
        url="/admin",
        status_code=303
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

    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "admin": admin,
            "urls": url_data
        }
    )
# ==========================================
# SIGN IN PAGE
# ==========================================

@app.get("/signin", response_class=HTMLResponse)
def signin_page(request: Request):

    return templates.TemplateResponse(
        request,
        "signin.html"
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
def counter_page(
    url_id: int,
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
# REDIRECT SHORT URL
# ==========================================

@app.get("/{short_code}")
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

    # 2. Get visitor information
    ip_address = request.client.host if request.client else None

    user_agent = request.headers.get("user-agent")

    # 3. Create a new click
    click = Click(
        url_id=url.id,
        ip_address=ip_address,
        user_agent=user_agent,
        is_monetized=False
    )

    # 4. Save the click in PostgreSQL
    db.add(click)
    db.commit()

    # 5. Redirect the visitor
    return RedirectResponse(
        url=url.original_url,
        status_code=307
    )

