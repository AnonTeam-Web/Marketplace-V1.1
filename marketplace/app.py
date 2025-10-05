from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.secret_key = "clef_secrete_pour_session"

# Liste des annonces/missions fictives
missions = []

# Comptes autorisés
allowed_usernames = ["Anon", "Gattaca", "PlaneteRouge", "Zone51", "BLR"]

# Stockage des utilisateurs
users = {}

# Décorateur pour forcer la connexion
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
        elif username in users:
            message = "Nom d'utilisateur déjà utilisé."
        else:
            role = "prof" if username == "BLR" else "team"
            users[username] = {
                "password": generate_password_hash(password),
                "email": email,
                "role": role
            }
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
        user = users.get(username)
        if user and check_password_hash(user["password"], password):
            session["user"] = username
            flash(f"Bienvenue {username} !", "success")
            return redirect(url_for("listing"))
        else:
            message = "Nom d'utilisateur ou mot de passe incorrect."
    return render_template("login.html", message=message)

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("Déconnexion réussie.", "info")
    return redirect(url_for("login"))

@app.route("/")
def home():
    session.pop("user", None)
    return redirect(url_for("login"))

@app.route("/listing")
@login_required
def listing():
    return render_template("listing.html", missions=missions)

@app.route("/create", methods=["GET", "POST"])
@login_required
def create():
    username = session["user"]
    if request.method == "POST":
        titre = request.form.get("titre")
        description = request.form.get("description")
        prix = int(request.form.get("prix"))
        date_butoir_str = request.form.get("date_butoir")
        quantity = int(request.form.get("quantity"))
        product_type = request.form.get("type")

        if not date_butoir_str:
            flash("Veuillez renseigner la date butoir.", "danger")
            return redirect(url_for("create"))
        date_butoir = datetime.strptime(date_butoir_str, "%Y-%m-%d").isoformat()

        mission_id = len(missions) + 1
        missions.append({
            "id": mission_id,
            "titre": titre,
            "description": description,
            "prix": prix,
            "vendeur": username,
            "date_butoir": date_butoir,
            "quantity": quantity,
            "type": product_type,
            "offres": []
        })
        flash("Annonce créée avec succès !", "success")
        return redirect(url_for("listing"))

    return render_template("create.html")

@app.route("/mission/<int:mission_id>", methods=["GET", "POST"])
@login_required
def mission_detail(mission_id):
    mission = next((m for m in missions if m["id"] == mission_id), None)
    if not mission:
        return "Annonce introuvable", 404

    message = None
    username = session["user"]

    if request.method == "POST":
        nouvelle_offre = int(request.form.get("prix"))
        if username == mission["vendeur"]:
            message = "Vous ne pouvez pas acheter votre propre annonce."
        else:
            # ✅ Offre libre, quel que soit le montant
            mission["offres"].append({"user": username, "prix": nouvelle_offre})
            message = f"Offre enregistrée : {nouvelle_offre} crédits !"

    return render_template("mission_detail.html", mission=mission, message=message)

@app.route("/mission/<int:mission_id>/accept_offer", methods=["POST"])
@login_required
def accept_offer(mission_id):
    mission = next((m for m in missions if m["id"] == mission_id), None)
    if not mission:
        return "Annonce introuvable", 404

    username = session["user"]
    if username != mission["vendeur"]:
        flash("Seul le vendeur peut accepter une offre.", "danger")
        return redirect(url_for("mission_detail", mission_id=mission_id))

    offer_user = request.form.get("user")
    offer_price = int(request.form.get("prix"))

    offre = next((o for o in mission["offres"] if o["user"] == offer_user and o["prix"] == offer_price), None)
    if not offre:
        flash("Offre introuvable.", "danger")
        return redirect(url_for("mission_detail", mission_id=mission_id))

    if mission["quantity"] > 0:
        mission["quantity"] -= 1
        mission["offres"].remove(offre)
        flash(f"Offre de {offer_user} acceptée pour {offer_price} crédits ! Qté restante : {mission['quantity']}", "success")
    else:
        flash("Stock insuffisant pour accepter cette offre.", "danger")

    return redirect(url_for("mission_detail", mission_id=mission_id))

# ✅ Nouvelle route : suppression d'une offre par son auteur
@app.route('/delete_offer/<int:mission_id>', methods=['POST'])
@login_required
def delete_offer(mission_id):
    user = session.get('user')
    prix = int(request.form['prix'])
    mission = next((m for m in missions if m['id'] == mission_id), None)

    if mission and 'offres' in mission:
        # Supprimer seulement si l'offre appartient à l'utilisateur et n'est pas acceptée
        mission['offres'] = [o for o in mission['offres'] if not (o['user'] == user and o['prix'] == prix and not o.get('accepted'))]
        flash("Votre offre a été supprimée.", "info")

    return redirect(url_for('mission_detail', mission_id=mission_id))

if __name__ == "__main__":
    app.run(debug=True)
