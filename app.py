import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import datetime, timedelta
import barcode
from barcode.writer import ImageWriter
import io
import csv

# --- CONFIGURAÇÃO INICIAL ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-longa-e-dificil-de-adivinhar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///estoque.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

if not os.path.exists('static/barcodes'):
    os.makedirs('static/barcodes')

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Por favor, faça login para acessar esta página.'
login_manager.login_message_category = 'info'

# --- MODELOS DO BANCO DE DADOS ---

class Loja(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_loja = db.Column(db.String(100), nullable=False, unique=True)
    usuarios = db.relationship('User', backref='loja', lazy=True)
    produtos = db.relationship('Produto', backref='loja', lazy=True)

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(128), nullable=False)
    nome_completo = db.Column(db.String(150), nullable=False)
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id'), nullable=False)
    is_owner = db.Column(db.Boolean, default=False)
    is_superadmin = db.Column(db.Boolean, default=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

class Produto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(150), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    categoria = db.Column(db.String(100), nullable=True)
    preco_base = db.Column(db.Float, nullable=False)
    loja_id = db.Column(db.Integer, db.ForeignKey('loja.id'), nullable=False)
    variacoes = db.relationship('ProdutoVariacao', backref='produto', lazy=True, cascade="all, delete-orphan")
    codigo_barras_geral_valor = db.Column(db.String(100), unique=True, nullable=True)
    codigo_barras_geral_img = db.Column(db.String(200), nullable=True)

class ProdutoVariacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    cor = db.Column(db.String(50), nullable=True)
    tamanho = db.Column(db.String(50), nullable=True)
    quantidade = db.Column(db.Integer, default=0)
    quantidade_minima = db.Column(db.Integer, default=5)
    codigo_barras_valor = db.Column(db.String(100), unique=True, nullable=True)
    codigo_barras_img = db.Column(db.String(200), nullable=True)
    historico = db.relationship('HistoricoEstoque', backref='variacao', lazy=True, cascade="all, delete-orphan")

class HistoricoEstoque(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_variacao_id = db.Column(db.Integer, db.ForeignKey('produto_variacao.id'), nullable=False)
    quantidade_movimentada = db.Column(db.Integer, nullable=False)
    quantidade_anterior = db.Column(db.Integer, nullable=False)
    quantidade_nova = db.Column(db.Integer, nullable=False)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    observacao = db.Column(db.String(255), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    usuario = db.relationship('User')
    preco_unitario_movimento = db.Column(db.Float, nullable=True)

# --- FUNÇÕES AUXILIARES E DECORATORS ---

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

def owner_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_owner and not current_user.is_superadmin:
            flash('Acesso restrito a donos de loja ou administradores.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_superadmin:
            flash('Acesso restrito a Super Administradores.', 'danger')
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def gerar_codigo_barras(valor, nome_arquivo_base):
    try:
        valor_numerico_puro = ''.join(filter(str.isdigit, valor))
        valor_para_ean = valor_numerico_puro.zfill(12)[:12]
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(valor_para_ean, writer=ImageWriter())

        # --- MUDANÇA PRINCIPAL AQUI ---

        # 1. Primeiro, definimos o nome completo do arquivo, incluindo a extensão.
        nome_final_do_arquivo = f"{nome_arquivo_base}.png"
        
        # 2. Criamos o caminho completo para onde o arquivo será salvo no disco.
        caminho_salvar_arquivo = os.path.join('static', 'barcodes', nome_final_do_arquivo)
        
        # 3. Passamos o caminho completo e exato para a função de escrita.
        # A biblioteca agora não precisa adivinhar a extensão.
        with open(caminho_salvar_arquivo, 'wb') as f:
            ean.write(f, options={'write_text': False})

        # 4. O caminho para salvar no banco de dados continua relativo à pasta 'static'.
        caminho_para_db = f'barcodes/{nome_final_do_arquivo}'
        
        return caminho_para_db, ean.get_fullcode()
        
    except Exception as e:
        print(f"Erro explícito ao gerar ou salvar código de barras para valor '{valor}': {e}")
        return None, None

# --- ROTAS DE AUTENTICAÇÃO ---
@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        username = request.form.get('username')
        password = request.form.get('password')
        nome_loja = request.form.get('nome_loja')
        if User.query.filter_by(username=username).first():
            flash('Este email já está cadastrado.', 'danger')
            return redirect(url_for('register'))
        if Loja.query.filter_by(nome_loja=nome_loja).first():
            flash('O nome desta loja já existe.', 'danger')
            return redirect(url_for('register'))
        nova_loja = Loja(nome_loja=nome_loja)
        db.session.add(nova_loja)
        db.session.commit()
        novo_usuario = User(nome_completo=nome_completo, username=username, loja_id=nova_loja.id, is_owner=True)
        novo_usuario.set_password(password)
        db.session.add(novo_usuario)
        db.session.commit()
        flash('Sua conta e loja foram criadas com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('index'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form.get('username')).first()
        if user and user.check_password(request.form.get('password')):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Login falhou. Verifique seu email e senha.', 'danger')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# --- ROTAS PRINCIPAIS DO SISTEMA ---

@app.route('/')
@login_required
def index():
    # CÁLCULO 1: VALOR TOTAL EM ESTOQUE
    total_estoque_valor = 0
    variacoes = ProdutoVariacao.query.join(Produto).filter(Produto.loja_id == current_user.loja_id).all()
    for v in variacoes:
        if v.quantidade > 0 and v.produto.preco_base:
            total_estoque_valor += v.quantidade * v.produto.preco_base

    # CÁLCULO 2: VALOR TOTAL VENDIDO
    total_vendas_valor = 0
    vendas = HistoricoEstoque.query.join(ProdutoVariacao).join(Produto).filter(
        Produto.loja_id == current_user.loja_id,
        HistoricoEstoque.quantidade_movimentada < 0,
        HistoricoEstoque.preco_unitario_movimento.isnot(None)
    ).all()
    for venda in vendas:
        total_vendas_valor += abs(venda.quantidade_movimentada) * venda.preco_unitario_movimento
        
    # CÁLCULO 3: DADOS PARA O GRÁFICO (Top 5 Produtos por Valor em Estoque)
    top_produtos_data = db.session.query(
        Produto.nome,
        func.sum(ProdutoVariacao.quantidade * Produto.preco_base).label('valor_total')
    ).join(ProdutoVariacao).filter(
        Produto.loja_id == current_user.loja_id, 
        ProdutoVariacao.quantidade > 0
    ).group_by(Produto.id).order_by(func.sum(ProdutoVariacao.quantidade * Produto.preco_base).desc()).limit(5).all()

    chart_labels = [row[0] for row in top_produtos_data]
    chart_values = [float(row[1]) for row in top_produtos_data]

    return render_template('index.html', 
                           total_estoque_valor=total_estoque_valor,
                           total_vendas_valor=total_vendas_valor,
                           total_produtos=Produto.query.filter_by(loja_id=current_user.loja_id).count(),
                           chart_labels=chart_labels,
                           chart_values=chart_values)

@app.route('/produtos')
@login_required
def produtos():
    query = request.args.get('query')
    categoria = request.args.get('categoria')
    produtos_query = Produto.query.filter_by(loja_id=current_user.loja_id)
    if query: produtos_query = produtos_query.filter(Produto.nome.ilike(f'%{query}%'))
    if categoria: produtos_query = produtos_query.filter_by(categoria=categoria)
    produtos = produtos_query.order_by(Produto.nome).all()
    categorias = db.session.query(Produto.categoria).filter_by(loja_id=current_user.loja_id).distinct().all()
    return render_template('produtos.html', produtos=produtos, categorias=[c[0] for c in categorias if c[0]])

@app.route('/adicionar_produto', methods=['GET', 'POST'])
@login_required
def adicionar_produto():
    if request.method == 'POST':
        novo_produto = Produto(nome=request.form.get('nome'), descricao=request.form.get('descricao'), categoria=request.form.get('categoria'), preco_base=float(request.form.get('preco_base')), loja_id=current_user.loja_id)
        db.session.add(novo_produto)
        db.session.flush()
        codigo_geral_valor = f'880{novo_produto.id:09}'
        codigo_geral_img_path, valor_ean_geral = gerar_codigo_barras(codigo_geral_valor, f"geral_{novo_produto.id}")
        novo_produto.codigo_barras_geral_valor = valor_ean_geral
        novo_produto.codigo_barras_geral_img = codigo_geral_img_path
        cores, tamanhos, quantidades, quantidades_minimas = request.form.getlist('cor[]'), request.form.getlist('tamanho[]'), request.form.getlist('quantidade[]'), request.form.getlist('quantidade_minima[]')
        for i in range(len(cores)):
            nova_variacao = ProdutoVariacao(produto_id=novo_produto.id, cor=cores[i], tamanho=tamanhos[i], quantidade=int(quantidades[i]), quantidade_minima=int(quantidades_minimas[i]))
            db.session.add(nova_variacao)
            db.session.flush()
            codigo_variacao_valor = f'890{novo_produto.id:04}{nova_variacao.id:05}'
            codigo_img_path, valor_ean_variacao = gerar_codigo_barras(codigo_variacao_valor, f"var_{nova_variacao.id}")
            nova_variacao.codigo_barras_valor = valor_ean_variacao
            nova_variacao.codigo_barras_img = codigo_img_path
        db.session.commit()
        flash('Produto e variações adicionados com sucesso!', 'success')
        return redirect(url_for('produtos'))
    return render_template('adicionar_produto.html')

@app.route('/produto_detalhe/<int:id>')
@login_required
def produto_detalhe(id):
    produto = db.session.get(Produto, id)
    if not produto or (produto.loja_id != current_user.loja_id and not current_user.is_superadmin):
        flash('Produto não encontrado ou acesso negado.', 'danger')
        return redirect(url_for('produtos'))
    return render_template('produto_detalhe.html', produto=produto)

# --- ROTAS DE EDIÇÃO E EXCLUSÃO ---
@app.route('/editar_produto/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_produto(id):
    produto = db.session.get(Produto, id)
    if not produto or produto.loja_id != current_user.loja_id:
        flash('Produto não encontrado ou acesso negado.', 'danger')
        return redirect(url_for('index'))
    if request.method == 'POST':
        produto.nome, produto.descricao, produto.categoria, produto.preco_base = request.form.get('nome'), request.form.get('descricao'), request.form.get('categoria'), float(request.form.get('preco_base'))
        variacoes_ids_existentes = []
        variacao_ids, cores, tamanhos, quantidades_minimas = request.form.getlist('variacao_id[]'), request.form.getlist('cor[]'), request.form.getlist('tamanho[]'), request.form.getlist('quantidade_minima[]')
        for i in range(len(cores)):
            if variacao_ids[i]:
                variacao_existente = db.session.get(ProdutoVariacao, int(variacao_ids[i]))
                if variacao_existente:
                    variacao_existente.cor, variacao_existente.tamanho, variacao_existente.quantidade_minima = cores[i], tamanhos[i], int(quantidades_minimas[i])
                    variacoes_ids_existentes.append(int(variacao_ids[i]))
            else:
                db.session.add(ProdutoVariacao(produto_id=produto.id, cor=cores[i], tamanho=tamanhos[i], quantidade=int(request.form.getlist('quantidade[]')[i]), quantidade_minima=int(quantidades_minimas[i])))
        for variacao in produto.variacoes:
            if variacao.id not in variacoes_ids_existentes:
                db.session.delete(variacao)
        db.session.commit()
        flash('Produto atualizado com sucesso!', 'success')
        return redirect(url_for('produto_detalhe', id=produto.id))
    return render_template('editar_produto.html', produto=produto)

@app.route('/excluir_produto/<int:id>', methods=['POST'])
@login_required
def excluir_produto(id):
    produto = db.session.get(Produto, id)
    if not produto or produto.loja_id != current_user.loja_id:
        flash('Produto não encontrado ou acesso negado.', 'danger')
        return redirect(url_for('index'))

    # --- NOVA LÓGICA DE EXCLUSÃO DE ARQUIVOS ---

    # 1. Antes de tudo, coletamos os nomes de todos os arquivos de imagem associados
    arquivos_a_excluir = []
    if produto.codigo_barras_geral_img:
        arquivos_a_excluir.append(produto.codigo_barras_geral_img)
    
    for variacao in produto.variacoes:
        if variacao.codigo_barras_img:
            arquivos_a_excluir.append(variacao.codigo_barras_img)

    # 2. Excluímos cada arquivo de imagem do disco
    for arquivo_relativo in arquivos_a_excluir:
        try:
            # Montamos o caminho completo para o arquivo (ex: 'static/barcodes/geral_1.png')
            caminho_completo = os.path.join('static', arquivo_relativo)
            if os.path.exists(caminho_completo):
                os.remove(caminho_completo)
                print(f"Arquivo de imagem '{caminho_completo}' excluído com sucesso.")
        except Exception as e:
            # Imprime um erro no console caso algo dê errado, mas não para a aplicação
            print(f"Erro ao excluir o arquivo de imagem '{caminho_completo}': {e}")
    
    # 3. SOMENTE AGORA, após apagar os arquivos, excluímos o registro do produto no banco de dados
    # A exclusão em cascata cuidará das variações e do histórico.
    db.session.delete(produto)
    db.session.commit()
    
    flash(f'O produto "{produto.nome}" e seus arquivos associados foram excluídos com sucesso.', 'success')
    return redirect(url_for('produtos'))

# --- ROTA DE AJUSTE DE ESTOQUE (MODAL) ---
@app.route('/ajustar_estoque/<int:variacao_id>', methods=['POST'])
@login_required
def ajustar_estoque(variacao_id):
    variacao = db.session.get(ProdutoVariacao, variacao_id)
    if not variacao or variacao.produto.loja_id != current_user.loja_id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))
    tipo_movimento = request.form.get('tipo_movimento')
    quantidade_movimentada = int(request.form.get('quantidade'))
    observacao = request.form.get('observacao')
    quantidade_anterior = variacao.quantidade
    if tipo_movimento == 'entrada':
        quantidade_nova = quantidade_anterior + quantidade_movimentada
    elif tipo_movimento == 'saida':
        quantidade_nova = quantidade_anterior - quantidade_movimentada
        if quantidade_nova < 0:
            flash('Não é possível ter estoque negativo.', 'danger')
            return redirect(request.referrer or url_for('index'))
    else:
        flash('Tipo de movimento inválido.', 'danger')
        return redirect(request.referrer or url_for('index'))
    variacao.quantidade = quantidade_nova
    historico = HistoricoEstoque(produto_variacao_id=variacao.id, quantidade_movimentada=quantidade_movimentada if tipo_movimento == 'entrada' else -quantidade_movimentada, quantidade_anterior=quantidade_anterior, quantidade_nova=quantidade_nova, observacao=observacao, user_id=current_user.id, preco_unitario_movimento=variacao.produto.preco_base)
    db.session.add(historico)
    db.session.commit()
    flash('Estoque atualizado com sucesso!', 'success')
    return redirect(request.referrer or url_for('index'))

# --- ROTAS DE GERENCIAMENTO DE USUÁRIOS E ADMIN ---
@app.route('/minha-equipe')
@login_required
@owner_required
def minha_equipe():
    usuarios = User.query.filter_by(loja_id=current_user.loja_id).all()
    return render_template('minha_equipe.html', usuarios=usuarios)

@app.route('/admin')
@login_required
@superadmin_required
def admin():
    total_lojas = Loja.query.count()
    total_usuarios = User.query.count()
    total_produtos = Produto.query.count()
    lojas = Loja.query.order_by(Loja.nome_loja).all()
    usuarios = User.query.options(db.joinedload(User.loja)).order_by(User.nome_completo).all()
    return render_template('admin.html', lojas=lojas, usuarios=usuarios, total_lojas=total_lojas, total_usuarios=total_usuarios, total_produtos=total_produtos)

@app.route('/admin/criar_loja', methods=['GET', 'POST'])
@login_required
@superadmin_required
def admin_criar_loja():
    if request.method == 'POST':
        nome_loja = request.form.get('nome_loja')
        if not nome_loja or Loja.query.filter_by(nome_loja=nome_loja).first():
            flash('Nome de loja inválido ou já existente.', 'danger')
            return redirect(url_for('admin_criar_loja'))
        nova_loja = Loja(nome_loja=nome_loja)
        db.session.add(nova_loja)
        db.session.commit()
        flash(f'Loja "{nome_loja}" criada com sucesso!', 'success')
        return redirect(url_for('admin'))
    return render_template('admin_criar_loja.html')

@app.route('/admin/criar_usuario', methods=['GET', 'POST'])
@login_required
@superadmin_required
def admin_criar_usuario():
    lojas = Loja.query.order_by(Loja.nome_loja).all()
    if request.method == 'POST':
        username = request.form.get('username')
        if not username or User.query.filter_by(username=username).first():
            flash('Email inválido ou já em uso.', 'danger')
            return redirect(url_for('admin_criar_usuario'))
        novo_usuario = User(nome_completo=request.form.get('nome_completo'), username=username, loja_id=request.form.get('loja_id'), is_owner='is_owner' in request.form)
        novo_usuario.set_password(request.form.get('password'))
        db.session.add(novo_usuario)
        db.session.commit()
        flash(f'Usuário "{novo_usuario.nome_completo}" criado com sucesso!', 'success')
        return redirect(url_for('admin'))
    return render_template('admin_criar_usuario.html', lojas=lojas)

# --- ROTAS DE LEITOR MOBILE E API ---
@app.route('/leitura_mobile')
@login_required
def leitura_mobile():
    return render_template('leitura_mobile.html')

@app.route('/api/buscar_por_codigo/<codigo>')
@login_required
def buscar_por_codigo(codigo):
    variacao = ProdutoVariacao.query.filter_by(codigo_barras_valor=codigo).first()
    if variacao and variacao.produto.loja_id == current_user.loja_id:
        return jsonify({'success': True, 'tipo': 'variacao', 'produto_nome': variacao.produto.nome, 'cor': variacao.cor, 'tamanho': variacao.tamanho, 'quantidade': variacao.quantidade, 'variacao_id': variacao.id})
    produto = Produto.query.filter_by(codigo_barras_geral_valor=codigo).first()
    if produto and produto.loja_id == current_user.loja_id:
        return jsonify({'success': True, 'tipo': 'produto_geral', 'produto_nome': produto.nome, 'produto_id': produto.id, 'total_variacoes': len(produto.variacoes)})
    return jsonify({'success': False, 'message': 'Código de barras não encontrado ou não pertence à sua loja.'})

# --- ROTAS DE RELATÓRIOS ---
@app.route('/relatorio/estoque_baixo')
@login_required
def relatorio_estoque_baixo():
    itens_estoque_baixo = db.session.query(ProdutoVariacao).join(Produto).filter(
        Produto.loja_id == current_user.loja_id,
        ProdutoVariacao.quantidade <= ProdutoVariacao.quantidade_minima
    ).order_by(Produto.nome).all()
    return render_template('relatorio_estoque_baixo.html', itens=itens_estoque_baixo)

@app.route('/relatorio/vendas_semanais')
@login_required
def relatorio_vendas_semanais():
    # 1. Define o período de tempo: de 7 dias atrás até agora.
    hoje = datetime.utcnow()
    uma_semana_atras = hoje - timedelta(days=7)

    # 2. Busca no histórico as movimentações de SAÍDA dentro do período
    vendas_semana = HistoricoEstoque.query.join(ProdutoVariacao).join(Produto).filter(
        Produto.loja_id == current_user.loja_id,
        HistoricoEstoque.quantidade_movimentada < 0, # Apenas saídas
        HistoricoEstoque.data_hora >= uma_semana_atras
    ).order_by(HistoricoEstoque.data_hora.desc()).all()

    # 3. Calcula os totais para o resumo
    total_vendido_valor = 0
    total_itens_vendidos = 0
    for venda in vendas_semana:
        if venda.preco_unitario_movimento: # Garante que o preço foi registrado
            total_vendido_valor += abs(venda.quantidade_movimentada) * venda.preco_unitario_movimento
        total_itens_vendidos += abs(venda.quantidade_movimentada)

    return render_template(
        'relatorio_vendas.html', 
        vendas=vendas_semana, 
        total_vendido_valor=total_vendido_valor, 
        total_itens_vendidos=total_itens_vendidos,
        data_inicio=uma_semana_atras,
        data_fim=hoje
    )

# app.py

@app.route('/relatorio/movimentacoes', methods=['GET', 'POST'])
@login_required
def relatorio_movimentacoes():
    # Define as datas padrão para a consulta inicial (últimos 30 dias)
    data_fim_obj = datetime.utcnow()
    data_inicio_obj = data_fim_obj - timedelta(days=30)

    # Se o formulário for enviado (POST), usa as datas fornecidas pelo usuário
    if request.method == 'POST':
        data_inicio_str = request.form.get('data_inicio')
        data_fim_str = request.form.get('data_fim')

        if data_inicio_str:
            data_inicio_obj = datetime.strptime(data_inicio_str, '%Y-%m-%d')

        if data_fim_str:
            # Adiciona 1 dia e subtrai 1 segundo para incluir o dia inteiro na busca
            data_fim_obj = datetime.strptime(data_fim_str, '%Y-%m-%d') + timedelta(days=1, seconds=-1)

    # Constrói a consulta base
    query = HistoricoEstoque.query.join(ProdutoVariacao).join(Produto).filter(
        Produto.loja_id == current_user.loja_id
    )

    # Aplica os filtros de data
    query = query.filter(HistoricoEstoque.data_hora.between(data_inicio_obj, data_fim_obj))

    # Executa a consulta
    movimentacoes = query.order_by(HistoricoEstoque.data_hora.desc()).all()

    return render_template(
        'relatorio_movimentacoes.html', 
        movimentacoes=movimentacoes,
        data_inicio=data_inicio_obj.strftime('%Y-%m-%d'),
        data_fim=data_fim_obj.strftime('%Y-%m-%d')
    )

# --- FUNCIONALIDADES ADICIONAIS ---
@app.route('/exportar_csv')
@login_required
def exportar_csv():
    produtos = Produto.query.filter_by(loja_id=current_user.loja_id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['ID Produto', 'Nome Produto', 'Categoria', 'Cor', 'Tamanho', 'Quantidade', 'Cod Barras Variação'])
    for produto in produtos:
        for variacao in produto.variacoes:
            writer.writerow([produto.id, produto.nome, produto.categoria, variacao.cor, variacao.tamanho, variacao.quantidade, variacao.codigo_barras_valor])
    output.seek(0)
    return send_file(io.BytesIO(output.getvalue().encode('utf-8')), mimetype='text/csv', as_attachment=True, download_name='relatorio_estoque.csv')

# --- INICIALIZAÇÃO E CRIAÇÃO DO DB ---
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not User.query.filter_by(is_superadmin=True).first():
            print("Criando Loja Matriz e usuário Super Admin...")
            admin_loja = Loja.query.filter_by(nome_loja='Loja Matriz Admin').first()
            if not admin_loja:
                admin_loja = Loja(nome_loja='Loja Matriz Admin')
                db.session.add(admin_loja)
                db.session.commit()
            admin_user = User(
                username='admin@admin.com', nome_completo='Super Administrador',
                loja_id=admin_loja.id, is_superadmin=True, is_owner=True
            )
            admin_user.set_password('admin123')
            db.session.add(admin_user)
            db.session.commit()
            print("Super Admin criado com sucesso! Email: admin@admin.com | Senha: admin123")
    
    app.run(debug=True, host='0.0.0.0', port=1234)