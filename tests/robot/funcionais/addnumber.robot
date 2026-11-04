*** Settings ***
Documentation     BrowserStack AddNumber. Com -v ROBO:True, o toque no botão ADD é físico.
Resource          ../resources/pages/addnumber.resource
Suite Setup       Abrir o AddNumber
Suite Teardown    Encerrar sessão com robô
Force Tags        addnumber


*** Test Cases ***
Abre com os campos vazios
    Element Should Be Visible    ${BOTAO_ADD}
    Resultado deve ser    Hello World!

Soma 7 + 5
    Somar    7    5
    Resultado deve ser    Answer: 12

Soma números negativos
    Somar    -3    10
    Resultado deve ser    Answer: 7
