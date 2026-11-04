*** Settings ***
Documentation     Rede instável: o app não pode fechar. O ApiDemos não usa rede em nenhuma tela
...               daqui, então o teste mostra resiliência do app, não comportamento de rede.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR    .view.List1
Suite Teardown    Fechar sessão NFR
Test Teardown     Restaurar rede
Test Tags         emulador


*** Test Cases ***
App sobrevive à perda de conectividade
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    Set Connectivity    wifi=False    data=False
    Sleep    2s
    App deve continuar vivo    ${pid}    ${crashes}
    Set Connectivity    airplane_mode=True
    Sleep    2s
    App deve continuar vivo    ${pid}    ${crashes}
    Set Connectivity    airplane_mode=False
    Set Connectivity    wifi=True    data=True
    Sleep    2s
    Rolar a tela
    App deve continuar vivo    ${pid}    ${crashes}

App sobrevive às mudanças de velocidade da rede
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    FOR    ${velocidade}    IN    gsm    edge    umts    lte    full
        Set Network Speed    ${velocidade}
        Rolar a tela
        App deve continuar vivo    ${pid}    ${crashes}
    END


*** Keywords ***
Restaurar rede
    Run Keyword And Ignore Error    Set Connectivity    airplane_mode=False
    Run Keyword And Ignore Error    Set Connectivity    wifi=True    data=True
    Run Keyword And Ignore Error    Set Network Speed    full
