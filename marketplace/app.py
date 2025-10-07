from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import os

# ---------------------------------------------------------
# 🔧 Configuration de l'application Flask
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = "clef_secrete_pour_session"

# Configuration base de données : locale (SQLite) ou Render (PostgreSQL)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Comptes autorisés
allowed_usernames = ["Anon", "Gattaca", "PlaneteRouge", "Zone51", "BLR"]

# ---------------------------------------------------------
# 🗂️ Modèles de base de données
# ---------------------------------------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False)

    missions = db.relationship("Mission", backref="vendeur", lazy=True)
    offres = db.relationship("Offer", backref="acheteur", lazy=True)


class Mission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    prix = db.Column(db.Float, nullable=False)
    date_butoir = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    type = db.Column(db.String(50))
    vendeur_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)

    offres = db.relationship("Offer", backref="mission", lazy=True, cascade="all, delete")


class Offer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    prix = db.Column(db.Float, nullable=False)
    accepted = db.Column(db.Boolean, default=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    mission_id = db.Column(db.Integer, db.ForeignKey("mission.id"), nullable=False)

# ---------------------------------------------------------
# 🧩 Décorateurs et contextes
# ---------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


@app.context_processor
def inject_user():
    return dict(current_user=session.get("user"))

# ---------------------------------------------------------
# 🔐 Authentification
# ---------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    message = None
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        email = request.form.get("email")

        if username.lower() != "blr":
            username = username.capitalize()

        if username not in allowed_usernames:
            message = "Nom d'utilisateur non autorisé."
        elif User.query.filter_by(username=username).first():
            message = "Nom d'utilisateur déjà utilisé."
        else:
            role = "prof" if username == "BLR" else "team"
            hashed_pw = generate_password_hash(password)
            new_user = User(username=username, password=hashed_pw, email=email, role=role)
            db.session.add(new_user)
            db.session.commit()
            flash("Compte créé avec succès ! Connectez-vous.", "success")
            return redirect(url_for("login"))
    return render_template("register.html", message=message, allowed_usernames=allowed_usernames)


@app.route("/login", methods=["GET", "POST"])
def login():
    message = None
    if request.method == "POST":
        username = request.form.get("username").strip()
        password = request.form.get("password")
        if username.lower() != "blr":
            username = username.capitalize()

        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user"] = username
            session["user_id"] = user.id
            flash(f"Bienvenue {username} !", "success")
            return redirect(url_for("listing"))
        else:
            message = "Nom d'utilisateur ou mot de passe incorrect."
    return render_template("login.html", message=message)


@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("user_id", None)
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("login"))


@app.route("/")
def home():
    session.pop("user", None)
    session.pop("user_id", None)
    return redirect(url_for("login"))

# ---------------------------------------------------------
# 📋 Missions
# ---------------------------------------------------------
@app.route("/listing")
@login_required
def listing():
    all_missions = Mission.query.all()
    return render_template("listing.html", missions=all_missions)


@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    user = User.query.filter_by(username=session["user"]).first()

    if request.method == "POST":
        titre = request.form.get("titre")
        description = request.form.get("description")
        prix = float(request.form.get("prix"))
        date_butoir_str = request.form.get("date_butoir")
        quantity = int(request.form.get("quantity"))
        product_type = request.form.get("type")

        if not date_butoir_str:
            flash("Veuillez renseigner la date butoir.", "danger")
            return redirect(url_for("create"))

        new_mission = Mission(
            titre=titre,
            description=description,
            prix=prix,
            date_butoir=date_butoir_str,
            quantity=quantity,
            type=product_type,
            vendeur_id=user.id
        )
        db.session.add(new_mission)
        db.session.commit()
        flash("Annonce créée avec succès !", "success")
        return redirect(url_for("listing"))

    return render_template("create.html")


@app.route("/mission/<int:mission_id>", methods=["GET", "POST"])
@login_required
def mission_detail(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    username = session["user"]
    message = None

    if request.method == "POST":
        nouvelle_offre = float(request.form.get("prix"))
        acheteur = User.query.filter_by(username=username).first()

        if acheteur.id == mission.vendeur_id:
            message = "Vous ne pouvez pas acheter votre propre annonce."
        else:
            new_offer = Offer(prix=nouvelle_offre, acheteur_id=acheteur.id, mission_id=mission.id)
            db.session.add(new_offer)
            db.session.commit()
            message = f"Offre enregistrée : {nouvelle_offre} crédits !"

    offres = Offer.query.filter_by(mission_id=mission.id).all()
    return render_template("mission_detail.html", mission=mission, message=message, offres=offres)


@app.route("/mission/<int:mission_id>/accept_offer", methods=["POST"])
@login_required
def accept_offer(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    vendeur = User.query.filter_by(username=session["user"]).first()

    if vendeur.id != mission.vendeur_id:
        flash("Seul le vendeur peut accepter une offre.", "danger")
        return redirect(url_for("mission_detail", mission_id=mission_id))

    offer_id = request.form.get("offer_id")
    offre = Offer.query.get(offer_id)

    if not offre:
        flash("Offre introuvable.", "danger")
        return redirect(url_for("mission_detail", mission_id=mission_id))

    if mission.quantity > 0:
        mission.quantity -= 1
        offre.accepted = True
        db.session.commit()
        flash(f"Offre de {offre.acheteur.username} acceptée pour {offre.prix} crédits ! Qté restante : {mission.quantity}", "success")
    else:
        flash("Stock insuffisant pour accepter cette offre.", "danger")

    return redirect(url_for("mission_detail", mission_id=mission_id))


# ✅ Suppression d'une offre par son auteur
@app.route('/delete_offer/<int:mission_id>', methods=['POST'])
@login_required
def delete_offer(mission_id):
    user = User.query.filter_by(username=session["user"]).first()
    prix = float(request.form["prix"])
    offre = Offer.query.filter_by(mission_id=mission_id, acheteur_id=user.id, prix=prix, accepted=False).first()

    if offre:
        db.session.delete(offre)
        db.session.commit()
        flash("Votre offre a été supprimée.", "info")

    return redirect(url_for("mission_detail", mission_id=mission_id))


# ---------------------------------------------------------
# 🚀 Lancement
# ---------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        # ✅ Crée toutes les tables si elles n'existent pas déjà
        db.create_all()
    app.run(debug=True)

