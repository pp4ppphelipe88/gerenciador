import os
from flask import Flask, render_template, request, redirect, url_for, flash, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from functools import wraps
from datetime import datetime
import barcode
from barcode.writer import ImageWriter
import io
import csv

# --- CONFIGURAÇÃO INICIAL ---
app = Flask(__name__)
app.config['SECRET_KEY'] = 'uma-chave-secreta-muito-longa-e-dificil-de-adivinhar'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///estoque.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Garante que a pasta de barcodes exista
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
    username = db.Column(db.String(100), nullable=False, unique=True) # Email
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

class ProdutoVariacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    produto_id = db.Column(db.Integer, db.ForeignKey('produto.id'), nullable=False)
    cor = db.Column(db.String(50), nullable=True)
    tamanho = db.Column(db.String(50), nullable=True)
    quantidade = db.Column(db.Integer, default=0)
    quantidade_minima = db.Column(db.Integer, default=5)
    codigo_barras_valor = db.Column(db.String(100), unique=True, nullable=True)
    codigo_barras_img = db.Column(db.String(200), nullable=True) # Caminho da imagem
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


# --- FUNÇÕES AUXILIARES E DECORATORS ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

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

def gerar_codigo_barras(valor, variacao_id):
    try:
        EAN = barcode.get_barcode_class('ean13')
        ean = EAN(valor, writer=ImageWriter())
        filename = f'static/barcodes/ean13_{variacao_id}'
        ean.write(filename)
        return f'{filename}.png'
    except Exception as e:
        print(f"Erro ao gerar código de barras: {e}")
        return None

# --- ROTAS DE AUTENTICAÇÃO ---

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        username = request.form.get('username') # Email
        password = request.form.get('password')
        nome_loja = request.form.get('nome_loja')

        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Este email já está cadastrado. Tente outro.', 'danger')
            return redirect(url_for('register'))

        loja_exists = Loja.query.filter_by(nome_loja=nome_loja).first()
        if loja_exists:
            flash('O nome desta loja já existe. Tente outro.', 'danger')
            return redirect(url_for('register'))

        nova_loja = Loja(nome_loja=nome_loja)
        db.session.add(nova_loja)
        db.session.commit()

        novo_usuario = User(
            nome_completo=nome_completo,
            username=username,
            loja_id=nova_loja.id,
            is_owner=True, # O primeiro usuário é o dono
            is_superadmin=False # Defina como True para o primeiro superadmin
        )
        novo_usuario.set_password(password)
        db.session.add(novo_usuario)
        db.session.commit()

        flash('Sua conta e loja foram criadas com sucesso! Faça o login.', 'success')
        return redirect(url_for('login'))
    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
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
    query = request.args.get('query')
    categoria = request.args.get('categoria')

    produtos_query = Produto.query.filter_by(loja_id=current_user.loja_id)

    if query:
        produtos_query = produtos_query.filter(Produto.nome.ilike(f'%{query}%'))
    if categoria:
        produtos_query = produtos_query.filter_by(categoria=categoria)
    
    produtos = produtos_query.order_by(Produto.nome).all()
    categorias = db.session.query(Produto.categoria).filter_by(loja_id=current_user.loja_id).distinct().all()
    
    return render_template('index.html', produtos=produtos, categorias=[c[0] for c in categorias if c[0]])


@app.route('/adicionar_produto', methods=['GET', 'POST'])
@login_required
def adicionar_produto():
    if request.method == 'POST':
        # Dados do produto principal
        nome = request.form.get('nome')
        descricao = request.form.get('descricao')
        categoria = request.form.get('categoria')
        preco_base = float(request.form.get('preco_base'))
        
        novo_produto = Produto(
            nome=nome,
            descricao=descricao,
            categoria=categoria,
            preco_base=preco_base,
            loja_id=current_user.loja_id
        )
        db.session.add(novo_produto)
        db.session.flush() # Para obter o ID do novo_produto antes do commit

        # Dados das variações
        cores = request.form.getlist('cor[]')
        tamanhos = request.form.getlist('tamanho[]')
        quantidades = request.form.getlist('quantidade[]')
        quantidades_minimas = request.form.getlist('quantidade_minima[]')

        for i in range(len(cores)):
            nova_variacao = ProdutoVariacao(
                produto_id=novo_produto.id,
                cor=cores[i],
                tamanho=tamanhos[i],
                quantidade=int(quantidades[i]),
                quantidade_minima=int(quantidades_minimas[i])
            )
            db.session.add(nova_variacao)
            db.session.flush() # para obter o id da variacao

            # Gerar código de barras
            # Um valor simples usando IDs para garantir unicidade
            codigo_valor = f'{novo_produto.id:04}{nova_variacao.id:04}{i:04}'
            codigo_img_path = gerar_codigo_barras(codigo_valor, nova_variacao.id)
            nova_variacao.codigo_barras_valor = codigo_valor
            nova_variacao.codigo_barras_img = codigo_img_path

        db.session.commit()
        flash('Produto e variações adicionados com sucesso!', 'success')
        return redirect(url_for('index'))

    return render_template('adicionar_produto.html')

@app.route('/produto_detalhe/<int:id>')
@login_required
def produto_detalhe(id):
    produto = Produto.query.get_or_404(id)
    # Garante que o usuário só possa ver produtos da sua loja
    if produto.loja_id != current_user.loja_id and not current_user.is_superadmin:
        flash('Produto não encontrado ou acesso negado.', 'danger')
        return redirect(url_for('index'))
    return render_template('produto_detalhe.html', produto=produto)


@app.route('/ajustar_estoque/<int:variacao_id>', methods=['GET', 'POST'])
@login_required
def ajustar_estoque(variacao_id):
    variacao = ProdutoVariacao.query.get_or_404(variacao_id)
    if variacao.produto.loja_id != current_user.loja_id:
        flash('Acesso negado.', 'danger')
        return redirect(url_for('index'))

    if request.method == 'POST':
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
                return redirect(url_for('ajustar_estoque', variacao_id=variacao_id))
        else:
            flash('Tipo de movimento inválido.', 'danger')
            return redirect(url_for('ajustar_estoque', variacao_id=variacao_id))

        # Atualiza o estoque
        variacao.quantidade = quantidade_nova
        
        # Cria o registro no histórico
        historico = HistoricoEstoque(
            produto_variacao_id=variacao.id,
            quantidade_movimentada=quantidade_movimentada if tipo_movimento == 'entrada' else -quantidade_movimentada,
            quantidade_anterior=quantidade_anterior,
            quantidade_nova=quantidade_nova,
            observacao=observacao,
            user_id=current_user.id
        )
        db.session.add(historico)
        db.session.commit()
        
        flash('Estoque atualizado com sucesso!', 'success')
        return redirect(url_for('produto_detalhe', id=variacao.produto_id))

    return render_template('ajustar_estoque.html', variacao=variacao)


# --- ROTAS DE GERENCIAMENTO DE USUÁRIOS ---

@app.route('/minha-equipe')
@login_required
@owner_required
def minha_equipe():
    usuarios = User.query.filter_by(loja_id=current_user.loja_id).all()
    return render_template('minha_equipe.html', usuarios=usuarios)

# ... (Rotas para adicionar/editar/remover usuários da equipe podem ser adicionadas aqui)

@app.route('/admin')
@login_required
@superadmin_required
def admin():
    # Coleta de dados para os KPIs do Dashboard
    total_lojas = Loja.query.count()
    total_usuarios = User.query.count()
    total_produtos = Produto.query.count()

    # Coleta de dados para as tabelas
    lojas = Loja.query.order_by(Loja.nome_loja).all()
    # Usamos um join para carregar a loja junto com o usuário e evitar múltiplas queries
    usuarios = User.query.options(db.joinedload(User.loja)).order_by(User.nome_completo).all()

    return render_template(
        'admin.html',
        lojas=lojas,
        usuarios=usuarios,
        total_lojas=total_lojas,
        total_usuarios=total_usuarios,
        total_produtos=total_produtos
    )

@app.route('/admin/criar_loja', methods=['GET', 'POST'])
@login_required
@superadmin_required
def admin_criar_loja():
    if request.method == 'POST':
        nome_loja = request.form.get('nome_loja')
        if not nome_loja:
            flash('O nome da loja é obrigatório.', 'danger')
            return redirect(url_for('admin_criar_loja'))

        loja_exists = Loja.query.filter_by(nome_loja=nome_loja).first()
        if loja_exists:
            flash('Uma loja com este nome já existe.', 'warning')
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
    # Passa a lista de lojas para o template para que o admin possa escolher
    lojas = Loja.query.order_by(Loja.nome_loja).all()

    if request.method == 'POST':
        nome_completo = request.form.get('nome_completo')
        username = request.form.get('username') # Email
        password = request.form.get('password')
        loja_id = request.form.get('loja_id')
        # Verifica se o checkbox 'is_owner' foi marcado
        is_owner = 'is_owner' in request.form

        user_exists = User.query.filter_by(username=username).first()
        if user_exists:
            flash('Este email já está em uso.', 'danger')
            return redirect(url_for('admin_criar_usuario'))

        novo_usuario = User(
            nome_completo=nome_completo,
            username=username,
            loja_id=loja_id,
            is_owner=is_owner,
            is_superadmin=False # Admin só cria usuários comuns ou donos de loja
        )
        novo_usuario.set_password(password)
        db.session.add(novo_usuario)
        db.session.commit()
        flash(f'Usuário "{nome_completo}" criado com sucesso!', 'success')
        return redirect(url_for('admin'))

    return render_template('admin_criar_usuario.html', lojas=lojas)
    

# --- FUNCIONALIDADES ADICIONAIS ---

@app.route('/exportar_csv')
@login_required
def exportar_csv():
    # Pega os produtos da loja do usuário logado
    produtos = Produto.query.filter_by(loja_id=current_user.loja_id).all()
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Cabeçalho do CSV
    cabecalho = [
        'ID Produto', 'Nome Produto', 'Categoria', 'Preço Base', 
        'ID Variação', 'Cor', 'Tamanho', 'Quantidade', 'Qtd Mínima', 'Código de Barras'
    ]
    writer.writerow(cabecalho)
    
    # Escreve os dados
    for produto in produtos:
        for variacao in produto.variacoes:
            linha = [
                produto.id, produto.nome, produto.categoria, produto.preco_base,
                variacao.id, variacao.cor, variacao.tamanho, variacao.quantidade,
                variacao.quantidade_minima, variacao.codigo_barras_valor
            ]
            writer.writerow(linha)
            
    output.seek(0)
    
    return send_file(
        io.BytesIO(output.getvalue().encode('utf-8')),
        mimetype='text/csv',
        as_attachment=True,
        download_name='relatorio_estoque.csv'
    )


# --- INICIALIZAÇÃO ---
if __name__ == '__main__':
    with app.app_context():
        # Cria o banco de dados e as tabelas se não existirem
        db.create_all()
        # Cria um superadmin na primeira execução, se não existir
        if not User.query.filter_by(is_superadmin=True).first():
            print("Criando usuário Super Admin...")
            admin_user = User(
                username='admin@admin.com',
                nome_completo='Super Administrador',
                loja_id=1, # Pode precisar criar uma loja 'Matriz' ou similar
                is_superadmin=True,
                is_owner=True
            )
            admin_user.set_password('admin123')
            
            # Cria uma loja padrão para o admin se não existir
            if not Loja.query.first():
                admin_loja = Loja(nome_loja='Loja Matriz Admin')
                db.session.add(admin_loja)
                db.session.commit()
                admin_user.loja_id = admin_loja.id
            
            db.session.add(admin_user)
            db.session.commit()
            print("Super Admin criado com sucesso! Email: admin@admin.com | Senha: admin123")

    app.run(debug=True, host='0.0.0.0', port=1234)