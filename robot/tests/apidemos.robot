*** Settings ***
Documentation     Navegação no ApiDemos só com cliques. Com -v ROBO:True, cada clique é um
...               toque físico da ponteira.
Resource          ../resources/pages/apidemos.resource
Suite Setup       Abrir o ApiDemos
Suite Teardown    Encerrar sessão com robô


*** Test Cases ***
Abre a tela inicial
    Tela inicial deve estar visível

Entra em Views
    Entrar em Views
    Tela Views deve estar visível

Volta para a tela inicial
    Voltar
    Tela inicial deve estar visível
