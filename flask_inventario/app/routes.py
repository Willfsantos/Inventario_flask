from flask import Blueprint, request, jsonify, render_template, Response, redirect, url_for, flash, make_response
from flask_login import login_required, current_user, login_user, logout_user
from functools import wraps
from models import db, Empresa, InventarioItem, User, Funcionario, HistoricoItem, ChamadoSuporte
from werkzeug.security import generate_password_hash, check_password_hash
import io
import csv
from datetime import date


bp = Blueprint('main', __name__)

# Decorador para controle de hierarquia (RBAC)
def role_required(*roles):
    def wrapper(fn):
        @wraps(fn)
        def decorated_view(*args, **kwargs):
            if current_user.role not in roles:
                return jsonify({'erro': 'Acesso negado'}), 403
            return fn(*args, **kwargs)
        return decorated_view
    return wrapper


########################## Registro / login #########################

@bp.route('/registro', methods=['POST'])
def registro():
    dados = request.json
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role', 'colaborador') # Pode vir 'admin' ou 'superadmin' na criação inicial
    empresa_id = dados.get('empresa_id')

    if User.query.filter_by(username=username).first():
        return jsonify({'erro': 'Usuário já existe'}), 400

    hashed_password = generate_password_hash(password)
    novo_usuario = User(username=username, password_hash=hashed_password, role=role, empresa_id=empresa_id)
    
    db.session.add(novo_usuario)
    db.session.commit()
    
    return jsonify({'msg': 'Usuário criado com sucesso!'}), 201

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # ATENÇÃO AQUI: Usar request.form em vez de request.json
        username = request.form.get('username')
        password = request.form.get('password')
        
        user = User.query.filter_by(username=username).first()
        
        # Lógica de verificação da senha
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for('main.index')) # Ou o nome correto da sua rota principal
        else:
            flash('Usuário ou senha inválidos.')
            return redirect(url_for('main.login'))
            
    return render_template('login.html')

@bp.route('/logout', methods=['GET', 'POST']) # <-- O segredo está em adicionar o 'GET' aqui
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))


# Rota onde o ADMIN define quais campos o formulário da sua empresa terá
@bp.route('/admin/configurar-form', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def configurar_form():
    dados = request.json
    
    # Valida se o usuário tem uma empresa vinculada (Superadmins por padrão não têm)
    if not current_user.empresa_id:
        return jsonify({'erro': 'Seu usuário não está vinculado a uma empresa para salvar formulários. Faça login com um usuário Admin.'}), 400
        
    empresa = Empresa.query.get(current_user.empresa_id)
    
    # Valida se a empresa realmente existe no banco
    if not empresa:
        return jsonify({'erro': 'Empresa não encontrada.'}), 404

    empresa.form_schema = dados.get('novo_schema', [])
    db.session.commit()
    
    return jsonify({'msg': 'Formulário customizado salvo com sucesso!'})

@bp.route('/admin/equipe', methods=['GET'])
@login_required
@role_required('admin')
def pagina_equipe():
    return render_template('equipe.html')

@bp.route('/admin/equipe/criar', methods=['POST'])
@login_required
@role_required('admin')
def criar_usuario_equipe():
    dados = request.json
    username = dados.get('username')
    password = dados.get('password')
    role = dados.get('role') # Recebe 'admin' ou 'colaborador'

    if User.query.filter_by(username=username).first():
        return jsonify({'erro': 'Usuário já existe'}), 400

    hashed_password = generate_password_hash(password)
    
    # Cria o usuário forçando a mesma empresa do admin atual
    novo_usuario = User(
        username=username, 
        password_hash=hashed_password, 
        role=role, 
        empresa_id=current_user.empresa_id 
    )
    
    db.session.add(novo_usuario)
    db.session.commit()
    
    return jsonify({'msg': f'Usuário criado com sucesso com acesso de {role}!'}), 201


############################ INVENTARIO ##################################

# Rota onde o COLABORADOR envia o item do inventário usando os campos definidos
@bp.route('/inventario/adicionar', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def adicionar_item():
    dados_preenchidos = request.json # Os dados dinâmicos validados no front-end
    
    novo_item = InventarioItem(
        empresa_id=current_user.empresa_id,
        criado_por=current_user.id,
        dados=dados_preenchidos
    )
    db.session.add(novo_item)
    db.session.commit()
    
    return jsonify({'msg': 'Item adicionado ao inventário!'})

@bp.route('/inventario/schema', methods=['GET'])
@login_required
def obter_schema():
    empresa = Empresa.query.get(current_user.empresa_id)
    if not empresa:
        return jsonify({'erro': 'Empresa não encontrada'}), 404
        
    return jsonify({'schema': empresa.form_schema})


# Rota para o painel de criação de formulários (Acesso do Admin)
@bp.route('/admin/formulario', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def pagina_admin_form():
    # Pega a empresa do administrador logado
    empresa = Empresa.query.get(current_user.empresa_id)

    if request.method == 'POST':
        # Salva o novo schema enviado pelo JavaScript
        empresa.form_schema = request.json
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(empresa, "form_schema")
        db.session.commit()
        return jsonify({'msg': 'Estrutura do inventário atualizada com sucesso!'})

    # ATENÇÃO: É esta linha abaixo que faltava enviar a variável "schema=empresa.form_schema"
    return render_template('admin_form.html', schema=empresa.form_schema)


# Rota para a tela de preenchimento do inventário (Acesso do Colaborador e acima)
@bp.route('/inventario', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def pagina_inventario():
    if not current_user.empresa_id:
        return "Usuário sem empresa vinculada", 400
        
    empresa = Empresa.query.get(current_user.empresa_id)
    
    # --- NOVA LÓGICA PARA SALVAR O POST ---
    if request.method == 'POST':
        dados_recebidos = request.json
        
        # Separa o ID do funcionário e limpa se for vazio
        status = dados_recebidos.pop('status', 'Em Estoque')
        funcionario_id = dados_recebidos.pop('funcionario_id', None)
        if status in ['Em Manutenção', 'Obsoleto/Sucata', 'Extraviado', 'Em Estoque']:
            funcionario_id = None

        if funcionario_id == "":
            funcionario_id = None
            
        # Cria o novo item no banco
        novo_item = InventarioItem(
            empresa_id=current_user.empresa_id,
            criado_por=current_user.id,
            funcionario_id=funcionario_id,
            status=status, # NOVO
            dados=dados_recebidos
        )
        
        db.session.add(novo_item)
        db.session.flush() # Força o SQLAlchemy a gerar o ID do novo_item antes do commit final
        
        # --- REGISTRA O HISTÓRICO DE CRIAÇÃO ---
        texto_detalhe = f"Cadastrado e atribuído ao ID {funcionario_id}" if funcionario_id else "Cadastrado no Estoque"
        log = HistoricoItem(
            item_id=novo_item.id,
            empresa_id=current_user.empresa_id,
            usuario_id=current_user.id,
            acao="Criado",
            detalhes=texto_detalhe
        )
        db.session.add(log)
        db.session.commit()
        return jsonify({'msg': 'Equipamento cadastrado com sucesso!'})
    # ----------------------------------------

    # Lógica do GET (carregar a tela)
    funcionarios = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).all()
    return render_template('inventario.html', schema=empresa.form_schema, funcionarios=funcionarios)

# Adicione no final do routes.py

@bp.route('/inventario/listar', methods=['GET'])
@login_required
@role_required('admin', 'superadmin') # Superadmin puro não tem empresa para listar itens
def listar_inventario():
    if not current_user.empresa_id:
        return "Usuário sem empresa vinculada", 400
        
    empresa = Empresa.query.get(current_user.empresa_id)
    itens = InventarioItem.query.filter_by(empresa_id=empresa.id).all()

    funcionarios = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).all()
    # Cria um mapa rápido de { ID : 'Nome do Funcionario' }
    dict_funcionarios = {f.id: f.nome for f in funcionarios}
    
    return render_template('lista_inventario.html', itens=itens, schema=empresa.form_schema, dict_funcionarios=dict_funcionarios)

@bp.route('/inventario/deletar/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin', 'superadmin')
def deletar_item(id):
    item = InventarioItem.query.get_or_404(id)
    
    # Valida se o item pertence à empresa do usuário logado
    if item.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado'}), 403
        
    db.session.delete(item)
    db.session.commit()
    return jsonify({'msg': 'Item excluído com sucesso!'})

@bp.route('/inventario/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def editar_item(id):
    item = InventarioItem.query.get_or_404(id)
    
    # Valida se o item pertence à empresa do usuário logado
    if item.empresa_id != current_user.empresa_id:
        if request.method == 'POST':
            return jsonify({'erro': 'Acesso negado'}), 403
        return "Acesso negado", 403
        
    empresa = Empresa.query.get(current_user.empresa_id)

    if request.method == 'POST':
        dados_recebidos = request.json
        
        # 1. Lê o status corretamente (Apenas UM pop)
        # Se não vier status do front, mantém o que já estava no item
        status_recebido = dados_recebidos.pop('status', item.status)
        
        # 2. Captura o novo ID do funcionário
        novo_func_id = dados_recebidos.pop('funcionario_id', None)
        if novo_func_id == "":
            novo_func_id = None
            
        # Regra de ouro: Se vinculou a alguém, o status muda automaticamente para 'Em Uso'
        if novo_func_id:
            status_recebido = 'Em Uso'
        # Se tirou o funcionário e estava 'Em Uso', volta para 'Em Estoque'
        elif status_recebido == 'Em Uso' and not novo_func_id:
            status_recebido = 'Em Estoque'

        # Trava de segurança: Se está quebrado/estoque, garante que não tenha dono
        if status_recebido in ['Obsoleto/Sucata', 'Extraviado', 'Em Estoque']:
            novo_func_id = None

        # Converte o ID para número (se existir)
        novo_func_id_int = int(novo_func_id) if novo_func_id else None

        # 3. Verifica se mudou de dono ANTES de sobrescrever o valor no banco
        mudou_dono = (item.funcionario_id != novo_func_id_int)
        
        # 4. Agora sim, atualiza as colunas reais do banco
        item.status = status_recebido
        item.funcionario_id = novo_func_id_int
        item.dados = dados_recebidos
        
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(item, "dados") # Força o SQLAlchemy a perceber a mudança no JSON
        
        # 5. Salva o Histórico de forma coerente
        if mudou_dono:
            acao_log = "Transferido"
            detalhes_log = f"Movido para funcionário ID {item.funcionario_id}" if item.funcionario_id else "Devolvido ao Estoque / Sem Vínculo"
        else:
            acao_log = "Editado"
            detalhes_log = "Dados do equipamento atualizados"

        log = HistoricoItem(
            item_id=item.id,
            empresa_id=current_user.empresa_id,
            usuario_id=current_user.id,
            acao=acao_log,
            detalhes=detalhes_log
        )
        
        db.session.add(log)
        db.session.commit()
        
        return jsonify({'msg': 'Item atualizado com sucesso!'})

    # Lógica do GET: Carrega a tela de edição preenchida
    funcionarios = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).all()
    return render_template('editar_inventario.html', item=item, schema=empresa.form_schema, funcionarios=funcionarios)

@bp.route('/inventario/exportar', methods=['GET'])
@login_required
@role_required('admin', 'superadmin')
def exportar_csv():
    if not current_user.empresa_id:
        return "Usuário sem empresa vinculada", 400
    
    empresa = Empresa.query.get(current_user.empresa_id)
    itens = InventarioItem.query.filter_by(empresa_id=empresa.id).all()

    si = io.StringIO()
    cw = csv.writer(si)

    cabecalhos = ['ID'] + [campo['nome_campo'] for campo in empresa.form_schema]
    cw.writerow(cabecalhos)

    for item in itens:
        linha = [item.id]
        for campo in empresa.form_schema:
            linha.append(item.dados.get(campo['nome_campo'], ''))
        cw.writerow(linha)

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=inventario.csv"}
    )


@bp.route('/inventario/importar', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def importar_csv():
    arquivo = request.files.get('arquivo_csv')
    
    if not arquivo or not arquivo.filename.endswith('.csv'):
        return jsonify({'erro': 'Por favor, envie um arquivo .csv válido.'}), 400

    try:
        # Decodifica o arquivo enviado e lê como um Dicionário
        stream = io.StringIO(arquivo.stream.read().decode("UTF8"), newline=None)
        csv_input = csv.DictReader(stream, delimiter=',')
        
        novos_itens = []
        for linha in csv_input:
            # Pega o status da planilha (se existir), senão força 'Em Estoque'
            status = linha.pop('status', 'Em Estoque')
            
            # Limpa colunas vazias
            linha_limpa = {k: v for k, v in linha.items() if v.strip()}
            
            novo_item = InventarioItem(
                empresa_id=current_user.empresa_id,
                criado_por=current_user.id,
                funcionario_id=None, # Itens em lote entram desvinculados por segurança
                status=status,
                dados=linha_limpa # Todas as outras colunas viram o JSON dinâmico
            )
            novos_itens.append(novo_item)
            
        db.session.add_all(novos_itens)
        db.session.commit()
        
        return jsonify({'msg': f'{len(novos_itens)} equipamentos importados com sucesso!'})
    except Exception as e:
        return jsonify({'erro': f'Erro ao processar arquivo. Verifique a formatação. Detalhes: {str(e)}'}), 500
    

@bp.route('/inventario/modelo-csv')
@login_required
@role_required('admin', 'superadmin')
def baixar_modelo_csv():
    empresa = Empresa.query.get(current_user.empresa_id)
    
    # Se a empresa não tiver um schema configurado, envia um cabeçalho padrão
    schema = empresa.form_schema or []
    
    # Monta o cabeçalho: a coluna 'status' é fixa, o resto vem do schema dinâmico
    cabecalho = ['status'] + [campo['nome_campo'] for campo in schema]
    
    # Cria o CSV em memória usando io.StringIO
    output = io.StringIO()
    writer = csv.writer(output, delimiter=',')
    writer.writerow(cabecalho) # Escreve apenas a linha de títulos
    
    # Prepara a resposta HTTP simulando um arquivo para download
    response = make_response(output.getvalue())
    response.headers["Content-Disposition"] = "attachment; filename=modelo_inventario.csv"
    response.headers["Content-type"] = "text/csv; charset=utf-8"
    
    return response

@bp.route('/inventario/termo/<int:id>')
@login_required
@role_required('admin', 'colaborador', 'superadmin')
def gerar_termo(id):
    item = InventarioItem.query.get_or_404(id)
    
    # Verifica se o item pertence à empresa atual
    if item.empresa_id != current_user.empresa_id:
        return "Acesso negado", 403
        
    # Só gera o termo se houver um funcionário vinculado
    if not item.funcionario_id:
        return "Erro: Este equipamento não está atribuído a nenhum funcionário.", 400
        
    empresa = Empresa.query.get(current_user.empresa_id)
    funcionario = Funcionario.query.get(item.funcionario_id)
    
    data_atual = date.today().strftime('%d/%m/%Y')
    
    return render_template(
        'termo_responsabilidade.html', 
        item=item, 
        empresa=empresa, 
        funcionario=funcionario, 
        data_atual=data_atual, 
        schema=empresa.form_schema
    )

@bp.route('/inventario/historico/<int:id>', methods=['GET'])
@login_required
@role_required('admin', 'superadmin')
def buscar_historico(id):
    # Verifica se o item é da empresa
    item = InventarioItem.query.get_or_404(id)
    if item.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado'}), 403
        
    logs = HistoricoItem.query.filter_by(item_id=id).order_by(HistoricoItem.data_hora.desc()).all()
    
    resultado = []
    for log in logs:
        resultado.append({
            'acao': log.acao,
            'detalhes': log.detalhes,
            'usuario': log.usuario.username if log.usuario else 'Sistema',
            'data': log.data_hora.strftime('%d/%m/%Y %H:%M')
        })
        
    return jsonify(resultado)

# Rota principal (Dashboard / Página inicial)
@bp.route('/')
@login_required
def index():
    if current_user.role == 'superadmin':
        total_empresas = Empresa.query.count()
        itens_alerta = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Em Manutenção').all()
        return render_template('index.html', total_empresas=total_empresas)
    
    # --- SE FOR COLABORADOR, ABRE O PORTAL DELE ---
    if current_user.role == 'colaborador':
        todos_funcionarios = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).all()
        funcionario_logado = None
        
        for f in todos_funcionarios:
            if f.dados:
                for chave, valor in f.dados.items():
                    # O '.lower()' garante que 'João@Email.com' seja lido igual a 'joao@email.com'
                    if chave.strip().lower() in ['email', 'e-mail', 'e mail']:
                        if valor.strip().lower() == current_user.username.strip().lower():
                            funcionario_logado = f
                            break
            if funcionario_logado:
                break
                
        if not funcionario_logado:
            return render_template('portal_colaborador.html', itens=[], erro="Seu usuário de login não encontrou o perfil de funcionário com o e-mail: " + current_user.username)
            
        meus_itens = InventarioItem.query.filter_by(funcionario_id=funcionario_logado.id).all()
        empresa = Empresa.query.get(current_user.empresa_id)
        return render_template('portal_colaborador.html', itens=meus_itens, funcionario=funcionario_logado, schema=empresa.form_schema, itens_alerta=itens_alerta)
    # ---------------------------------------------------

    # Código antigo do Admin continua aqui para baixo...
    total_itens = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id).count()
    total_usuarios = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).count()
    qtd_estoque = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Em Estoque').count()
    qtd_uso = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Em Uso').count()
    qtd_manutencao = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Em Manutenção').count()
    qtd_sucata = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Obsoleto/Sucata').count()
    qtd_extraviado = InventarioItem.query.filter_by(empresa_id=current_user.empresa_id, status='Extraviado').count()

    return render_template('index.html', total_itens=total_itens, total_usuarios=total_usuarios,
                           qtd_estoque=qtd_estoque, qtd_uso=qtd_uso, qtd_manutencao=qtd_manutencao,
                           qtd_sucata=qtd_sucata, qtd_extraviado=qtd_extraviado)


# --- ROTAS DO SUPERADMIN ---

@bp.route('/superadmin', methods=['GET'])
@login_required
@role_required('superadmin')
def pagina_superadmin():
    return render_template('superadmin.html')

@bp.route('/superadmin/empresa', methods=['POST'])
@login_required
@role_required('superadmin')
def criar_empresa():
    dados = request.json
    nome = dados.get('nome')
    
    if Empresa.query.filter_by(nome=nome).first():
        return jsonify({'erro': 'Empresa já existe'}), 400
        
    nova_empresa = Empresa(nome=nome)
    db.session.add(nova_empresa)
    db.session.commit()
    
    return jsonify({'msg': 'Empresa criada com sucesso!', 'id': nova_empresa.id}), 201

@bp.route('/api/empresas', methods=['GET'])
@login_required
@role_required('superadmin')
def listar_empresas():
    empresas = Empresa.query.all()
    return jsonify([{'id': e.id, 'nome': e.nome} for e in empresas])

@bp.route('/funcionarios', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def gerenciar_funcionarios():
    if not current_user.empresa_id:
        return "Acesso negado", 403

    empresa = Empresa.query.get(current_user.empresa_id)

    if request.method == 'POST':
        dados_recebidos = request.json
        nome = dados_recebidos.pop('nome') 
        senha = dados_recebidos.pop('senha_acesso', None) # Captura e remove a senha
        
        # Procura o campo de e-mail dentro dos dados dinâmicos
        email_encontrado = None
        for chave, valor in dados_recebidos.items():
            if chave.strip().lower() in ['email', 'e-mail', 'e mail']:
                email_encontrado = valor.strip()
                break
                
        if not email_encontrado:
            return jsonify({'erro': "O formulário precisa ter um campo de 'Email' preenchido para gerar o acesso."}), 400

        # Verifica se já existe login com este e-mail
        usuario_existente = User.query.filter_by(username=email_encontrado).first()
        if usuario_existente:
            return jsonify({'erro': "Este e-mail já possui um login de acesso cadastrado."}), 400

        # 1. Salva o Funcionario
        novo_func = Funcionario(nome=nome, dados=dados_recebidos, empresa_id=current_user.empresa_id)
        db.session.add(novo_func)

        # 2. Salva o Login do Colaborador (Removido o campo 'email=')
        novo_usuario = User(
            username=email_encontrado,
            password_hash=generate_password_hash(senha),
            role='colaborador',
            empresa_id=current_user.empresa_id
        )
        db.session.add(novo_usuario)

        db.session.commit()
        return jsonify({'msg': 'Funcionário e acesso de login criados com sucesso!'})

    lista = Funcionario.query.filter_by(empresa_id=current_user.empresa_id).all()
    return render_template('funcionarios.html', funcionarios=lista, schema=empresa.funcionario_form_schema or [])

@bp.route('/funcionarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def editar_funcionario(id):
    func = Funcionario.query.get_or_404(id)
    
    if func.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado.'}), 403

    # Se for GET, apenas devolve os dados para preencher o formulário na tela
    if request.method == 'GET':
        return jsonify({
            'nome': func.nome,
            'dados': func.dados or {}
        })

    # Se for POST, salva as alterações
    if request.method == 'POST':
        dados_recebidos = request.json
        nome = dados_recebidos.pop('nome')
        nova_senha = dados_recebidos.pop('senha_acesso', None)
        
        # Encontra o e-mail antigo (para achar o usuário de login)
        email_antigo = None
        if func.dados:
            for k, v in func.dados.items():
                if k.strip().lower() in ['email', 'e-mail', 'e mail']:
                    email_antigo = v.strip()
                    break

        # Procura qual foi o NOVO e-mail digitado
        email_novo = None
        for k, v in dados_recebidos.items():
            if k.strip().lower() in ['email', 'e-mail', 'e mail']:
                email_novo = v.strip()
                break
                
        if not email_novo:
            return jsonify({'erro': "O campo de Email não pode ficar vazio."}), 400

        # Se o email mudou, verifica se já não pertence a outra pessoa
        if email_novo != email_antigo:
            usuario_existente = User.query.filter_by(username=email_novo).first()
            if usuario_existente:
                return jsonify({'erro': "Este novo e-mail já está em uso por outro login."}), 400

        # 1. Atualiza os dados do Funcionário
        func.nome = nome
        func.dados = dados_recebidos
        
        # 2. Atualiza o Usuário de Login usando o username
        if email_antigo:
            usuario = User.query.filter_by(username=email_antigo).first()
            if usuario:
                usuario.username = email_novo
                # Só altera a senha se o admin digitou uma nova
                if nova_senha: 
                    usuario.password_hash = generate_password_hash(nova_senha)

        db.session.commit()
        return jsonify({'msg': 'Colaborador e acesso atualizados com sucesso!'})

@bp.route('/funcionarios/deletar/<int:id>', methods=['DELETE'])
@login_required
@role_required('admin', 'superadmin')
def deletar_funcionario(id):
    func = Funcionario.query.get_or_404(id)
    
    if func.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado.'}), 403

    # Trava de Segurança: Impede excluir se ele tiver equipamentos
    itens_vinculados = InventarioItem.query.filter_by(funcionario_id=func.id).count()
    if itens_vinculados > 0:
        return jsonify({'erro': f'Este funcionário possui {itens_vinculados} equipamento(s) vinculado(s). Desvincule-os primeiro.'}), 400

    # Tenta encontrar o e-mail nos dados dinâmicos para excluir também o Login
    if func.dados:
        email_encontrado = None
        for chave, valor in func.dados.items():
            if chave.strip().lower() in ['email', 'e-mail', 'e mail']:
                email_encontrado = valor.strip()
                break
                
        if email_encontrado:
            # Busca pelo username em vez de email
            usuario = User.query.filter_by(username=email_encontrado).first()
            if usuario:
                db.session.delete(usuario)

    # Exclui o perfil do funcionário
    db.session.delete(func)
    db.session.commit()
    
    return jsonify({'msg': 'Funcionário e acesso removidos com sucesso!'})


@bp.route('/admin/formulario_funcionario', methods=['GET', 'POST'])
@login_required
@role_required('admin', 'superadmin')
def configurar_form_funcionario():
    empresa = Empresa.query.get(current_user.empresa_id)
    
    if request.method == 'POST':
        empresa.funcionario_form_schema = request.json
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(empresa, "funcionario_form_schema")
        db.session.commit()
        return jsonify({'msg': 'Formulário de funcionários atualizado!'})
        
    # ATENÇÃO AQUI: Esta linha deve estar alinhada com o "if", e não dentro dele!
    return render_template('admin_form_func.html', schema=empresa.funcionario_form_schema)

@bp.route('/funcionarios/promover/<int:id>', methods=['POST'])
@login_required
@role_required('admin', 'superadmin')
def promover_admin(id):
    funcionario = Funcionario.query.get_or_404(id)
    
    # Valida se o funcionário é da mesma empresa do Admin logado
    if funcionario.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado'}), 403
        
    # Pega o e-mail de dentro do JSON do funcionário
    email_func = None
    if funcionario.dados:
        for chave, valor in funcionario.dados.items():
            if chave.strip().lower() in ['email', 'e-mail', 'e mail']:
                email_func = valor.strip()
                break
                
    if not email_func:
        return jsonify({'erro': 'Funcionário sem e-mail cadastrado.'}), 400
        
    # Busca o login (User) usando o e-mail encontrado e a empresa
    usuario = User.query.filter_by(username=email_func, empresa_id=current_user.empresa_id).first()
    
    if not usuario:
        return jsonify({'erro': 'Nenhum login de acesso encontrado para este funcionário.'}), 404
        
    if usuario.role == 'admin':
        return jsonify({'erro': 'Este funcionário já é um administrador.'}), 400
        
    # Promove o usuário
    usuario.role = 'admin'
    db.session.commit()
    
    return jsonify({'msg': f'Sucesso! {funcionario.nome} agora é um Administrador.'})


@bp.route('/inventario/reportar/<int:id>', methods=['POST'])
@login_required
def reportar_problema(id):
    item = InventarioItem.query.get_or_404(id)
    
    if item.empresa_id != current_user.empresa_id:
        return jsonify({'erro': 'Acesso negado'}), 403

    dados = request.json
    descricao = dados.get('descricao', '')

    if not descricao:
        return jsonify({'erro': 'Você precisa descrever o problema.'}), 400

    # Muda o status automaticamente para o Admin ver que quebrou
    item.status = 'Em Manutenção'

    # Grava o aviso no histórico do equipamento
    log = HistoricoItem(
        item_id=item.id,
        empresa_id=current_user.empresa_id,
        usuario_id=current_user.id,
        acao="Problema Relatado",
        detalhes=f"Relato do colaborador: {descricao}"
    )
    
    db.session.add(log)
    db.session.commit()
    
    return jsonify({'msg': 'Problema reportado! O Administrador foi notificado.'})
