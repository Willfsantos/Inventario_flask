from flask import Flask
from models import db, User
from routes import bp
from flask_login import LoginManager
import os

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = 'SECRET-KEY-INVENTORY'
    # Substitua pelas suas credenciais do PostgreSQL
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'inventario.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    login_manager = LoginManager()
    login_manager.login_view = 'main.login' # Define para onde redirecionar se não estiver logado
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    db.init_app(app)
    
    # Registra as rotas
    app.register_blueprint(bp)

    with app.app_context():
        db.create_all() # Cria as tabelas na primeira execução

    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True)