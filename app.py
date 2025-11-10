from flask import Flask, request, render_template, redirect, current_app, url_for, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.exc import IntegrityError
from flask_cors import CORS
from flask_swagger_ui import get_swaggerui_blueprint
from datetime import datetime
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
import os
import requests

app = Flask(__name__)

basedir = os.path.abspath(os.path.dirname(__file__))
SECRET_KEY = os.urandom(32)
app.secret_key = SECRET_KEY
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'videotheek.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
# app.config['SERVER_NAME'] = '141.252.48.223:5000'

CORS(app)

SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.yaml'
API_KEY = "3f09bc75"
TMDB_SEARCH_URL = "https://api.themoviedb.org/3/search/movie"
TMDB_POPULAR_URL = "https://api.themoviedb.org/3/movie/popular"

db = SQLAlchemy(app)

swagger_ui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={'app_name': "Aapie de API aap)"}
)

app.register_blueprint(swagger_ui_blueprint, url_prefix=SWAGGER_URL)

def get_movie_details(title):
    url = f"http://www.omdbapi.com/?t={title}&apikey={API_KEY}"
    response = requests.get(url)
    movie_data = response.json()

    print(movie_data)
    
    if movie_data.get('Response') == 'True':
        description = movie_data.get('Plot', 'Geen beschrijving beschikbaar')
        image = movie_data.get('Poster', 'https://via.placeholder.com/150')
        return description, image
    else:
        return 'Geen beschrijving beschikbaar', 'https://via.placeholder.com/150'

class Film(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(150), nullable=False)
    status = db.Column(db.String(50), nullable=False)  
    description = db.Column(db.String(500), nullable=True) 
    image = db.Column(db.String(500), nullable=True)  

# !! Maak een class voor de gebruikers aan zodat er geregistreert en ingelogt kan worden zodat er een tabel beschikbaar is in de database
# Zorg ervoor dat deze gekoppeld word aan de logging tabel om ook te laten zien welke gebruiker een actie uitvoert

class Logging(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    film_id = db.Column(db.Integer, db.ForeignKey('film.id'), nullable=False)
    action = db.Column(db.String, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default = datetime.now())
    user = db.Column(db.String, db.ForeignKey('user.username'), nullable=False)

def _log_action(film_id, action, user):
    log = Logging(film_id=film_id, action=action, user=user, timestamp=datetime.now())
    db.session.add(log)
    db.session.commit()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), nullable=False, unique=True)
    password = db.Column(db.String(150), nullable=False)
    role = db.Column(db.String(100), nullable=False, default = 'user')

def get_id(user): 
    return user.id
    
# Aanmaken database
with app.app_context():
    db.create_all()

login_manager = LoginManager()
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@login_manager.unauthorized_handler
def unauthorized_handler():
  flash('You need to login to access this page.', 'warning') 
  return redirect(url_for('DENIED'))

# Routes
@app.route('/')
def home():
    return render_template('home.html')

@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin():
    if current_user.role != 'admin':
        flash('You do not have permission to access this page.', 'danger')
        return redirect(url_for('DENIED'))

    film = Film.query.all()
    return render_template('admin.html', film=film)

@app.route('/dashboard')
def dashboard():
    user = User.query.all()
    return render_template('dashboard.html', user=user)

@app.route('/api/videotheek')
def apivid():
    film = Film.query.all()
    films = [{'id': Film.id, 'title': Film.title} for Film in film]
    return jsonify(films)

@app.route('/videotheek', methods=['GET', 'POST'])
@login_required
def videotheek():
    film = Film.query.all()
    return render_template('videotheek.html', film=film)  

@app.route('/login', methods=['GET', 'POST'])
def inloggen():
    if request.method == 'POST':
        username = request.form['username']
        
        user = User.query.filter_by(username=username).first()

        if user:
            if user.password == request.form.get("password"):
                login_user(user)
                flash('Succesvol ingelogd')
                return redirect(url_for('dashboard'))
            else:
                flash('Verkeerde wachtwoord')
                return render_template('login.html')
        else:
            flash('Verkeerde gebruikersnaam')
            return render_template('login.html')
    else:
        return render_template('login.html')
    
@app.route('/reserve', methods=['POST'])
def reserve():
    if request.accept_mimetypes.best == 'application/json':
        data = request.json
        film_id = data.get('id')
        if not film_id:
            return jsonify({"error": "Geen film ID opgegeven"}), 400

        film = Film.query.get(film_id)
        if not film:
            return jsonify({"error": "Film niet gevonden"}), 404

        if film.status == 'Beschikbaar':
            film.status = 'Gereserveerd'
            db.session.commit()
            return jsonify({"message": 'De film is gereserveerd'}), 200
        else:
            return jsonify({"error": 'De film is al gereserveerd'}), 400
    else:
        film_id = request.form.get('id')
        film = Film.query.get(film_id)
        if not film:
            flash('Film niet gevonden', 'danger')
        else:
            if film.status == 'Beschikbaar':
                film.status = 'Gereserveerd'
                db.session.commit()
                _log_action(film.id, "Gereserveerd", current_user.username)
                flash(f'Film "{film.title}" is gereserveerd!', 'success')
            else:
                flash(f'Film "{film.title}" is al gereserveerd!', 'danger')
        return redirect(url_for('videotheek'))

@app.route('/return', methods=['POST'])
def return_film():
    if request.accept_mimetypes.best == 'application/json':
        data = request.json
        film_id = data.get('id')
        if not film_id:
            return jsonify({"error": "Geen film ID opgegeven"}), 400

        film = Film.query.get(film_id)
        if not film:
            return jsonify({"error": "Film niet gevonden"}), 404

        if film.status == 'Gereserveerd':
            film.status = 'Beschikbaar'
            db.session.commit()
            return jsonify({"message": "Film is teruggebracht"}), 200
        else:
            return jsonify({"error": "Film is niet gereserveerd"}), 400
    else:
        film_id = request.form.get('id')
        film = Film.query.get(film_id)
        if not film:
            flash('Film niet gevonden', 'danger')
        else:
            if film.status == 'Gereserveerd':
                film.status = 'Beschikbaar'
                db.session.commit()
                _log_action(film.id, "Teruggebracht", current_user.username)
                flash('De film is teruggebracht!', 'success')
            else:
                flash('De film is niet gereserveerd.', 'danger')
        return redirect(url_for('videotheek'))

@app.route('/edit', methods=['GET', 'POST', 'PUT'])
def edit():
    if request.accept_mimetypes.best == 'application/json':
        data = request.json
        film_id = data.get('id')
        title = data.get('title')
        status = data.get('status')

        if not film_id:
            return jsonify({"error": "Geen film ID opgegeven"}), 400

        film = Film.query.get(film_id)
        if not film:
            return jsonify({"error": "Film niet gevonden"}), 404

        if title:
            description, image = get_movie_details(title)
            film.title = title
            film.status = status
            film.description = description
            film.image = image
            db.session.commit()
            return jsonify({"message": "Film succesvol bijgewerkt"}), 200
        else:
            return jsonify({"error": "Titel is verplicht"}), 400
    else:
        film_id = request.form.get('id')
        film = Film.query.get(film_id)
        if not film:
            flash('Film niet gevonden', 'danger')
            return redirect(url_for('videotheek')) 

        if request.method == 'POST':
            title = request.form['title']
            status = request.form['status']
            if title:
                description, image = get_movie_details(title)
                film.title = title
                film.status = status
                film.description = description
                film.image = image
                db.session.commit()
                _log_action(film.id, "Bijgewerkt", current_user.username)
                flash('De film is bijgewerkt!', 'success')
                return redirect(url_for('videotheek'))

            flash('Titel is verplicht!', 'danger')

        return render_template('edit.html', film=film)

@app.route('/add', methods=['GET', 'POST'])
def add():
    if request.accept_mimetypes.best == 'application/json':
        data = request.json
        title = data.get('title')
        status = data.get('status')
        if not title:
            return jsonify({"error": "Titel is verplicht"}), 400

        description, image = get_movie_details(title)
        new_film = Film(title=title, status=status, description=description, image=image)
        db.session.add(new_film)
        db.session.commit()
        return jsonify({"message": "Film succesvol toegevoegd"}), 201
    else:
        if request.method == 'POST':
            title = request.form['title']
            status = request.form['status']
            if title:
                description, image = get_movie_details(title)
                new_film = Film(title=title, status=status, description=description, image=image)
                db.session.add(new_film)
                db.session.commit()
                _log_action(new_film.id, "Toegevoegd", current_user.username)
                flash('De film is toegevoegd!', 'success')
                return redirect(url_for('admin'))

            flash('Titel is verplicht!', 'danger')

        return render_template('add.html')

@app.route('/delete', methods=['POST', 'DELETE'])
def delete():
    if request.accept_mimetypes.best == 'application/json':
        data = request.json
        film_id = data.get('id')
        if not film_id:
            return jsonify({"error": "Geen film ID opgegeven"}), 400

        film = Film.query.get(film_id)
        if not film:
            return jsonify({"error": "Film niet gevonden"}), 404

        try:
            db.session.delete(film)
            db.session.commit()
            return jsonify({"message": "Film succesvol verwijderd"}), 200
        except IntegrityError:
            return jsonify({"error": "Fout bij het verwijderen van de film"}), 500
    else:
        film_id = request.form.get('id')
        film = Film.query.get(film_id)
        if not film:
            flash('Film niet gevonden', 'danger')
        else:
            try:
                db.session.delete(film)
                db.session.commit()
                _log_action(film_id, "Verwijderd", current_user.username)
                flash('De film is succesvol verwijderd!', 'success')
            except IntegrityError:
                flash('Er is een fout opgetreden tijdens het verwijderen van de film.', 'danger')

        return redirect(url_for('videotheek'))


@app.route('/register', methods=['GET', 'POST'])
def registreren():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        try:
            newuser = User(username=username, password=password)
            db.session.add(newuser)
            db.session.commit()
            flash('Gefeliciteerd je hebt een account')
            return redirect(url_for('inloggen'))
        except IntegrityError:
            db.session.rollback()
            return render_template(url_for('registreren'))
    else:
        return render_template('register.html')

@app.route('/logout')
def uitloggen():
    logout_user()
    return redirect(url_for("home"))

@app.route('/opdracht')
def opdracht():
    return render_template('opdracht.html')

@app.route('/DENIED')
def DENIED():
    return render_template('DENIED.html')

#voeg een route toe waar je bij komt op moment dat je naar een url gaat waar je geen toegang tot hebt.
#bijvoorbeeld op moment dat je naar de videotheek wil als je niet ingelogd bent

if __name__ == '__main__':
    app.run(debug=True)