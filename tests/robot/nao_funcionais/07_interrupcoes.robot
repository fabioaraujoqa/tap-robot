*** Settings ***
Documentation     Chamada, SMS e segundo plano: o texto digitado precisa continuar na tela.
...               Chamada e SMS simulados só existem em emulador.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir o ApiDemos
Suite Teardown    Fechar sessão NFR
Test Setup        Preencher formulário
Test Tags         emulador


*** Variables ***
${CAMPO_SALVO}    id=io.appium.android.apis:id/saved
${TEXTO}          texto preservado
${TELEFONE}       5551234567


*** Test Cases ***
Estado preservado após chamada
    Gsm Call    ${TELEFONE}    call
    Sleep    3s
    Gsm Call    ${TELEFONE}    cancel
    Sleep    3s
    Estado deve estar preservado

Estado preservado após SMS
    Send Sms    ${TELEFONE}    Mensagem de teste
    Sleep    3s
    Estado deve estar preservado

Estado preservado após segundo plano
    Background Application    3
    Estado deve estar preservado


*** Keywords ***
Preencher formulário
    Abrir Activity    ${PACOTE}    .app.SaveRestoreState
    Wait Until Element Is Visible    ${CAMPO_SALVO}    10s
    Clear Text    ${CAMPO_SALVO}
    Input Text    ${CAMPO_SALVO}    ${TEXTO}
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    Set Test Variable    ${PID_INICIAL}    ${pid}
    Set Test Variable    ${CRASHES_INICIAIS}    ${crashes}

Estado deve estar preservado
    App deve continuar vivo    ${PID_INICIAL}    ${CRASHES_INICIAIS}
    Element Text Should Be    ${CAMPO_SALVO}    ${TEXTO}
