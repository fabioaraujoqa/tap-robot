*** Settings ***
Documentation     Toque físico pelo robô (P1S) quando ROBO=True; clique por software quando não.
...
...               robot -d results tests/robot/e2e                                  clique por software
...               robot -d results -v ROBO:True tests/robot/e2e                     toque físico
...               robot -d results -v ROBO:True -v SIMULADO:True tests/robot/e2e    robô simulado (sem P1S)
...
...               No modo simulado o toque não acontece de verdade, então "Clicar" também clica
...               por software para o teste seguir; o G-code de cada toque fica no log.
Resource          base.resource


*** Keywords ***
Iniciar sessão com robô
    [Documentation]    Sessão Appium + conexão com o robô (se ROBO=True).
    [Arguments]    &{app}
    IF    ${ROBO}    Conectar Robô    udid=${UDID}
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

Tocar em coordenada
    [Documentation]    Toque físico (ROBO=True) ou por software num ponto da tela, em pixels.
    [Arguments]    ${x}    ${y}
    IF    ${ROBO}    Toque Físico Em Coordenada    ${x}    ${y}
    IF    not ${ROBO} or ${SIMULADO}
        Tap With Positions    100ms    ${{(int(${x}), int(${y}))}}
    END

Arrastar
    [Documentation]    Arraste físico (ROBO=True) ou por software entre dois pontos, em pixels.
    [Arguments]    ${x1}    ${y1}    ${x2}    ${y2}    ${duracao}=0.8
    IF    ${ROBO}    Arraste Físico    ${x1}    ${y1}    ${x2}    ${y2}    ${duracao}
    IF    not ${ROBO} or ${SIMULADO}
        Swipe    start_x=${x1}    start_y=${y1}    end_x=${x2}    end_y=${y2}    duration=${duracao}s
    END

Arrastar entre elementos
    [Documentation]    Encosta, espera e arrasta. Serve para telas que pedem toque longo.
    [Arguments]    ${origem}    ${destino}
    IF    ${ROBO}    Arraste Físico Entre Elementos    ${origem}    ${destino}
    IF    not ${ROBO} or ${SIMULADO}    Drag And Drop    ${origem}    ${destino}
