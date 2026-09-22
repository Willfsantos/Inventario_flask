from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime
#from sqlalchemy.dialects.postgresql import JSONB

db = SQLAlchemy()

class Empresa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    
    # O form_schema do inventário
    form_schema = db.Column(db.JSON, default=list)
    
    # O form_schema dos funcionários FICA AQUI NA EMPRESA
    funcionario_form_schema = db.Column(db.JSON, default=list)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False) # 'superadmin', 'admin', 'colaborador'
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=True)
    empresa = db.relationship('Empresa', backref='usuarios')

class InventarioItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    criado_por = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=True)
    status = db.Column(db.String(50), default='Em Estoque')
    dados = db.Column(db.JSON, default=dict)
    # Os dados preenchidos pelo colaborador com base no form_schema
    

class Funcionario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    
    # Os DADOS preenchidos do funcionário FICAM AQUI
    dados = db.Column(db.JSON, default=dict)
    
    equipamentos = db.relationship('InventarioItem', backref='funcionario_vinculado', lazy=True)

class HistoricoItem(db.Model):
    __tablename__ = 'historico_item'
    
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey('inventario_item.id', ondelete='CASCADE'), nullable=False)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    usuario_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False) # Quem fez a ação
    acao = db.Column(db.String(50), nullable=False) # Ex: "Criado", "Transferido", "Editado"
    detalhes = db.Column(db.Text, nullable=True) # Ex: "Transferido de Estoque para João"
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Relacionamentos para facilitar a exibição
    usuario = db.relationship('User', backref='historicos_feitos')

class ChamadoSuporte(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    empresa_id = db.Column(db.Integer, db.ForeignKey('empresa.id'), nullable=False)
    item_id = db.Column(db.Integer, db.ForeignKey('inventariO_item_id'), nullable=False)
    funcionario_id = db.Column(db.Integer, db.ForeignKey('funcionario.id'), nullable=False)
    descricao = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(25), default='Aberto')
    data_criacao = db.Column(db.DateTime, default=db.func.current_timestamp())