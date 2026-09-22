# criar_superadmin.py
from app import create_app
from models import db, User
from werkzeug.security import generate_password_hash

app = create_app()

with app.app_context():
    # Defina seu usuário e senha aqui
    usuario = 'superadmin'
    senha = '123' 

    if not User.query.filter_by(username=usuario).first():
        senha_hash = generate_password_hash(senha)
        
        # Superadmin não precisa estar vinculado a uma empresa (empresa_id=None)
        novo_superadmin = User(
            username=usuario, 
            password_hash=senha_hash, 
            role='superadmin', 
            empresa_id=None 
        )
        
        db.session.add(novo_superadmin)
        db.session.commit()
        print(f"Superadmin '{usuario}' criado com sucesso!")
    else:
        print(f"O usuário '{usuario}' já existe no banco.")