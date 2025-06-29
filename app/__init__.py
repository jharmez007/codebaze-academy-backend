from flask import Flask
from .config import Config
from .extensions import db, migrate, jwt
from .routes import auth, student, admin, courses

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)

    app.register_blueprint(auth.bp)
    app.register_blueprint(courses.bp, url_prefix='/courses')
    # app.register_blueprint(student.bp, url_prefix='/student')
    # app.register_blueprint(admin.bp, url_prefix='/admin')

    return app
