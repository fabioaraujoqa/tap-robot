*** Settings ***
Documentation     Gestos para os testes não funcionais: um fluxo que toca e arrasta, sem validar
...               o que aparece na tela. Com -v ROBO:True, cada gesto só passa se o celular sentir
...               o contato da ponteira.
Resource          ../resources/pages/apidemos.resource
Suite Setup       Abrir o ApiDemos
Suite Teardown    Encerrar sessão com robô
Test Tags         e2e


*** Test Cases ***
Bolinhas com toques e arrastes
    Abrir Bouncing Balls
    Tocar em coordenada    360    600
    Tocar em coordenada    200    900
    Arrastar    150    500    570    1100
    Arrastar    570    500    150    1100
    Go Back
    Voltar ao menu inicial

Arrastar um ponto até outro
    Abrir Drag and Drop
    Arrastar entre elementos    ${PONTO_1}    ${PONTO_2}
    Go Back
    Voltar ao menu inicial
