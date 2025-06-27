# 💻 Gerenciador de Clientes em Linha de Comando

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?style=for-the-badge&logo=python)

## 📝 Descrição

Este é um sistema simples de gerenciamento de clientes, desenvolvido em Python para ser executado diretamente no terminal (linha de comando). O objetivo do projeto é permitir o controle de uma lista de clientes, oferecendo funcionalidades básicas de um CRUD (Criar, Ler, Atualizar e Excluir).

---

## ✨ Funcionalidades

O sistema oferece as seguintes opções:

* **Adicionar Cliente:** Cadastra um novo cliente com nome, e-mail e telefone.
* **Listar Clientes:** Exibe todos os clientes cadastrados.
* **Buscar Cliente:** Procura por um cliente específico pelo nome.
* **Excluir Cliente:** Remove um cliente da lista pelo nome.
* **Salvar Dados:** Os dados dos clientes são armazenados em um arquivo `clientes.txt` para persistência.

---

## 🛠️ Tecnologias Utilizadas

O projeto foi construído utilizando apenas recursos nativos do Python, sem a necessidade de bibliotecas externas.

* **[Python](https://www.python.org/)**

---

## 🚀 Como Usar

Para executar este projeto em sua máquina local, siga os passos abaixo.

### Pré-requisitos

* Você precisa ter o [Python](https://www.python.org/downloads/) (versão 3.8 ou superior) instalado em seu computador.

### Passos para Execução

1.  **Clone o repositório:**
    Abra o seu terminal e use o comando `git clone` para baixar os arquivos do projeto.

    ```bash
    git clone [https://github.com/pp4ppphelipe88/gerenciador.git](https://github.com/pp4ppphelipe88/gerenciador.git)
    ```

2.  **Navegue até o diretório do projeto:**
    ```bash
    cd gerenciador
    ```

3.  **Execute o programa:**
    Uma vez dentro da pasta, execute o script principal.

    ```bash
    python gerenciador_clientes.py
    ```

4.  **Interaja com o menu:**
    Após a execução, um menu interativo será exibido no terminal, permitindo que você escolha a operação desejada.

    ```
    ----- Gerenciador de Clientes -----
    1. Adicionar Cliente
    2. Listar Clientes
    3. Buscar Cliente
    4. Excluir Cliente
    5. Sair
    -----------------------------------
    ```

---

## 📂 Estrutura do Projeto

O projeto está organizado da seguinte forma:

gerenciador/
│
├── gerenciador_clientes.py   # Arquivo principal que contém toda a lógica do programa.
├── clientes.txt              # Arquivo de texto onde os dados dos clientes são salvos.
└── README.md                 # Este arquivo de documentação.


* `gerenciador_clientes.py`: Contém as funções para carregar, salvar, adicionar, listar, buscar e excluir clientes, além do menu principal que interage com o usuário.
* `clientes.txt`: É criado automaticamente na primeira vez que um cliente é adicionado e serve como um banco de dados simples para o sistema.

---

## 👨‍💻 Autor

Este projeto foi desenvolvido por:

* **Raposa** - [pp4ppphelipe88](https://github.com/pp4ppphelipe88)
