from flask import Flask, render_template, request, redirect, url_for, session, flash, abort
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import os, math, smtplib
from email.message import EmailMessage

# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "clef_secrete_pour_session")

# DATABASE_URL environment variable expected (Render) else fallback to sqlite local
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///local.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# Comptes autorisés
allowed_usernames = ["Anon", "Gattaca", "PlaneteRouge", "Zone51", "BLR"]

# ---------------------------------------------------------
# Modèles de base de données
# ---------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120))
    role = db.Column(db.String(20), nullable=False)

    missions = db.relationship("Mission", backref="vendeur", lazy=True)
    offres = db.relationship("Offer", backref="acheteur", lazy=True)


class Mission(db.Model):
    __tablename__ = "missions"
    id = db.Column(db.Integer, primary_key=True)
    titre = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=False)
    prix = db.Column(db.Float, nullable=False)           # prix de vente
    prix_achat = db.Column(db.Float, nullable=True)     # Prix d'achat (pour les 'donnee')
    date_butoir = db.Column(db.String(50), nullable=False)
    quantity = db.Column(db.Integer, default=1)
    type = db.Column(db.String(50))                     # ex: 'donnee', 'carte', 'mission', 'option'
    data_label = db.Column(db.String(20), nullable=True) # 'U' ou 'non_classifie' (pour type 'donnee')
    vendeur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    offres = db.relationship("Offer", backref="mission", lazy=True, cascade="all, delete")

    @property
    def reduction_percent(self):
        # retourne float arrondi à 1 décimale si réduction, sinon None
        if self.prix_achat and self.prix_achat > 0 and self.prix < self.prix_achat:
            pct = 100 * (self.prix_achat - self.prix) / self.prix_achat
            return round(pct, 1)
        return None


class Offer(db.Model):
    __tablename__ = "offers"
    id = db.Column(db.Integer, primary_key=True)
    prix = db.Column(db.Float, nullable=False)
    accepted = db.Column(db.Boolean, default=False)
    acheteur_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    mission_id = db.Column(db.Integer, db.ForeignKey("missions.id"), nullable=False)

# ---------------------------------------------------------
# Utilitaires : envoi d'e-mails simple (SMTP)
# ---------------------------------------------------------
def send_email(to_address, subject, body):
    smtp_server = os.environ.get("SMTP_SERVER")
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_user = os.environ.get("SMTP_USER")
    smtp_pass = os.environ.get("SMTP_PASS")
    sender = os.environ.get("SENDER_EMAIL")

    if not (smtp_server and smtp_user and smtp_pass and sender):
        app.logger.warning("SMTP non configuré — e-mail non envoyé")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = to_address
    msg.set_content(body)

    try:
        with smtplib.SMTP(smtp_server, smtp_port, timeout=10) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True
    except Exception as e:
        app.logger.exception("Erreur envoi e-mail: %s", e)
        return False

def send_invoice_email(seller_email, buyer_email, mission, offer_price):
    blr = os.environ.get("BLR_EMAIL")
    subject = f"Facture - vente : {mission.titre}"
    body = (f"Facture de vente\n\n"
            f"Article : {mission.titre}\n"
            f"Vendeur : {mission.vendeur.username} ({seller_email})\n"
            f"Acheteur ID : {buyer_email}\n"
            f"Prix de vente : {offer_price} crédits\n"
            f"Date : {datetime.utcnow().isoformat()}Z\n\n"
            f"Merci.")
    # envoyer au vendeur
    if seller_email:
        send_email(seller_email, subject, body)
    # envoyer à l'acheteur
    if buyer_email:
        send_email(buyer_email, subject, body)
    # envoyer à BLR si configuré
    if blr:
        send_email(blr, subject, f"[Copie BLR]\n\n{body}")

# ---------------------------------------------------------
# Décorateur et context injection
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
# Routes d'auth
# ---------------------------------------------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    message = None
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
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
        username = (request.form.get("username") or "").strip()
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
# Listing / Create
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
    if not user:
        abort(403)

    if request.method == "POST":
        titre = request.form.get("titre")
        description = request.form.get("description")
        prix = float(request.form.get("prix"))
        date_butoir_str = request.form.get("date_butoir")
        quantity = int(request.form.get("quantity"))
        product_type = request.form.get("type")  # 'donnee' ou autre

        # Si type 'donnee' => prix_achat + label obligatoire
        prix_achat = None
        data_label = None
        if product_type == "donnee":
            prix_achat_raw = request.form.get("prix_achat")
            data_label = request.form.get("data_label")  # 'U' or 'non_classifie'
            if not prix_achat_raw or not data_label:
                flash("Pour les données, vous devez renseigner le prix d'achat et le label.", "danger")
                return redirect(url_for("create"))
            prix_achat = float(prix_achat_raw)

            # si label U : impose prix de vente <= 2.15 * prix_achat
            if data_label == "U" and prix > 2.15 * prix_achat:
                flash("Pour les données labellisées U, le prix de vente ne peut pas être supérieur à 2,15 × le prix d'achat.", "danger")
                return redirect(url_for("create"))

        if not date_butoir_str:
            flash("Veuillez renseigner la date butoir.", "danger")
            return redirect(url_for("create"))

        new_mission = Mission(
            titre=titre,
            description=description,
            prix=prix,
            prix_achat=prix_achat,
            date_butoir=date_butoir_str,
            quantity=quantity,
            type=product_type,
            data_label=data_label,
            vendeur_id=user.id
        )
        db.session.add(new_mission)
        db.session.commit()
        flash("Annonce créée avec succès !", "success")
        return redirect(url_for("listing"))

    return render_template("create.html")


# ---------------------------------------------------------
# Détails mission, offres, suppression, acceptation
# ---------------------------------------------------------
@app.route("/mission/<int:mission_id>", methods=["GET", "POST"])
@login_required
def mission_detail(mission_id):
    mission = Mission.query.get_or_404(mission_id)
    username = session["user"]
    message = None

    if request.method == "POST":
        # Faire une offre : règles spéciales si type 'donnee'
        nouvelle_offre = float(request.form.get("prix"))
        acheteur = User.query.filter_by(username=username).first()
        if not acheteur:
            abort(403)

        # Empêcher acheteur = vendeur
        if acheteur.id == mission.vendeur_id:
            message = "Vous ne pouvez pas acheter votre propre annonce."
        else:
            # Si mission de type 'donnee' et label présent, appliquer règles
            if mission.type == "donnee":
                if mission.data_label == "U":
                    # Aucun minimum pour offre mais si l'offre égale au prix du vendeur => auto accept
                    if math.isclose(nouvelle_offre, mission.prix):
                        # création de l'offre acceptée + décrémentation
                        auto_offer = Offer(prix=nouvelle_offre, acheteur_id=acheteur.id, mission_id=mission.id, accepted=True)
                        db.session.add(auto_offer)
                        if mission.quantity > 0:
                            mission.quantity -= 1
                        db.session.commit()
                        # Envoi facture au vendeur, acheteur, BLR
                        seller = mission.vendeur
                        send_invoice_email(seller.email, acheteur.email, mission, nouvelle_offre)
                        message = f"Offre acceptée automatiquement pour {nouvelle_offre} crédits (label U)."
                    else:
                        # Offre normale acceptée into offers list (not accepted)
                        new_offer = Offer(prix=nouvelle_offre, acheteur_id=acheteur.id, mission_id=mission.id)
                        db.session.add(new_offer)
                        db.session.commit()
                        message = f"Offre enregistrée : {nouvelle_offre} crédits !"
                else:
                    # label non_classifie -> min offer = ceil(0.55 * prix_achat)
                    if not mission.prix_achat:
                        message = "Erreur : prix d'achat introuvable pour cette donnée."
                    else:
                        min_offer = math.ceil(0.55 * mission.prix_achat)
                        if nouvelle_offre < min_offer:
                            message = f"Pour les données non classifiées, l'offre minimale est {min_offer} crédits."
                        else:
                            new_offer = Offer(prix=nouvelle_offre, acheteur_id=acheteur.id, mission_id=mission.id)
                            db.session.add(new_offer)
                            db.session.commit()
                            message = f"Offre enregistrée : {nouvelle_offre} crédits !"
            else:
                # Produit non-donnée : aucune contrainte
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
        # Envoi facture au vendeur, acheteur et BLR
        buyer = offre.acheteur
        seller = mission.vendeur
        send_invoice_email(seller.email, buyer.email, mission, offre.prix)
        flash(f"Offre de {buyer.username} acceptée pour {offre.prix} crédits ! Qté restante : {mission.quantity}", "success")
    else:
        flash("Stock insuffisant pour accepter cette offre.", "danger")

    return redirect(url_for("mission_detail", mission_id=mission_id))


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
# Page légales (CGV/CGU/RGPD)
# ---------------------------------------------------------

@app.route("/legal")
def legal():
    # Crée une page simple — personnalise le template 'legal.html'
    return render_template("legal.html")
@app.route('/upgrade_db')
def upgrade_db():
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            # Ajoute colonne prix_achat
            conn.execute(text("""
                ALTER TABLE missions ADD COLUMN IF NOT EXISTS prix_achat NUMERIC;
            """))
            # Ajoute colonne data_label
            conn.execute(text("""
                ALTER TABLE missions ADD COLUMN IF NOT EXISTS data_label VARCHAR(50);
            """))
        return "✅ Colonnes ajoutées ou déjà présentes (Render compatible)."
    except Exception as e:
        return f"❌ Erreur lors de la mise à niveau : {e}"

@app.route('/upgrade_db')
def upgrade_db():
    from sqlalchemy import text
    try:
        with db.engine.connect() as conn:
            # Ajoute colonne prix_achat
            conn.execute(text("""
                ALTER TABLE missions ADD COLUMN IF NOT EXISTS prix_achat NUMERIC;
            """))
            # Ajoute colonne data_label
            conn.execute(text("""
                ALTER TABLE missions ADD COLUMN IF NOT EXISTS data_label VARCHAR(50);
            """))
        return "✅ Colonnes ajoutées ou déjà présentes (Render compatible)."
    except Exception as e:
        return f"❌ Erreur lors de la mise à niveau : {e}"


# ---------------------------------------------------------
# Lancement
# ---------------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)


