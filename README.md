# URLShortener - Monetized URL Shortener

## 📌 Description

URLShortener est une application web permettant de raccourcir
des URLs et de suivre les clics générés.

Le projet intègre un système d'interstitial avec compte à rebours,
un système de tracking des clics, une logique anti-fraude et
un système de monétisation.

L'application possède également un espace administrateur permettant
de consulter les statistiques et l'historique des liens.

---

## 🚀 Technologies utilisées

### Backend

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL
- Jinja2

### Frontend

- HTML5
- CSS3
- JavaScript

### Sécurité

- SessionMiddleware
- Password hashing avec bcrypt
- Variables d'environnement
- Protection anti-fraude basée sur l'adresse IP

---

## 📂 Structure du projet

```text
URLShortener/
│
├── main.py
├── database.py
├── requirements.txt
├── .env
├── .gitignore
├── README.md
│
├── models/
│   ├── url.py
│   ├── click.py
│   ├── user.py
│   └── admin.py
│
├── services/
│   ├── anti_fraud.py
│   └── ...
│
├── utils/
│   ├── base62.py
│   └── short_code.py
│
├── templates/
│   ├── index.html
│   ├── login.html
│   ├── signin.html
│   ├── admin.html
│   └── counter.html
│
└── static/
    └── css/
        └── style.css



