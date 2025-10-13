# init_db.py
import os
from app import db, app
from urllib.parse import urlparse

url = os.environ.get("DATABASE_URL")
print("DATABASE_URL (env) =", url)

if url and url.startswith("postgres://"):
    print("Remplacement de 'postgres://' par 'postgresql://'")
    url = url.replace("postgres://", "postgresql://", 1)
    os.environ["DATABASE_URL"] = url  # met à jour pour SQLAlchemy si besoin

# Afficher la config SQLAlchemy effective
print("SQLALCHEMY_DATABASE_URI used by runtime:", app.config.get("SQLALCHEMY_DATABASE_URI"))

with app.app_context():
    try:
        db.create_all()
        print("Tables créées avec succès !")
    except Exception as e:
        print("Erreur lors de db.create_all():")
        import traceback; traceback.print_exc()
        print("Si la base distante n'est pas accessible, vérifie la DATABASE_URL et la présence de la DB.")
