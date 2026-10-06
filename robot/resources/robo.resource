*** Settings ***
Documentation     Toque físico pelo robô (P1S) quando ROBO=True; clique por software quando não.
...
...               robot -d results robot/tests                                  clique por software
...               robot -d results -v ROBO:True robot/tests                     toque físico
...               robot -d results -v ROBO:True -v SIMULADO:True robot/tests    robô simulado (sem P1S)
...
...               No modo simulado o toque não acontece de verdade, então "Clicar" também clica
...               por software para o teste seguir; o G-code de cada toque fica no log.
Resource          base.resource


*** Keywords ***
Iniciar sessão com robô
    [Documentation]    Sessão Appium + conexão com o robô (se ROBO=True).
    [Arguments]    &{app}
    IF    ${ROBO}    Conectar Robô
    Iniciar sessão    &{app}

Encerrar sessão com robô
    Run Keyword And Ignore Error    Fechar sessão
    IF    ${ROBO}    Desconectar Robô

Clicar
    [Documentation]    Toque físico no centro do elemento (ROBO=True) ou clique normal.
    [Arguments]    ${locator}
    IF    ${ROBO}
        Toque Físico No Elemento    ${locator}
        IF    ${SIMULADO}    Click Element    ${locator}
    ELSE
        Click Element    ${locator}
    END
