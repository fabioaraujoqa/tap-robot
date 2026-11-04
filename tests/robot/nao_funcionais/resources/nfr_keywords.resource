*** Settings ***
Documentation     Sessão, abertura de telas, coleta e limites da suíte não funcional.
...               Sessão, servidor e aparelho vêm de base.resource; os gestos, de robo.resource.
Library           Collections
Library           nfr_appium.py
Variables         nfr_limites.py
Resource          ../../resources/pages/apidemos.resource


*** Variables ***
${PACOTE}         io.appium.android.apis
${INICIAL}        .ApiDemos


*** Keywords ***
Abrir sessão NFR
    [Documentation]    Abre o ApiDemos pelo UiAutomator2 e confere se o shell está liberado.
    [Arguments]    ${activity}=${INICIAL}
    Abrir o ApiDemos
    Adb Shell    true
    ${bloqueada}=    Tela Bloqueada
    IF    ${bloqueada}    Fail    O aparelho está bloqueado: desbloqueie e rode de novo.
    Abrir Activity    ${PACOTE}    ${activity}

Fechar sessão NFR
    Encerrar sessão com robô

Registrar amostra
    [Documentation]    Mede o aparelho e grava uma linha no CSV do tipo informado.
    [Arguments]    ${tipo}    ${inicio}    ${evento}=${EMPTY}
    ${amostra}=    Coletar Amostra    ${PACOTE}
    ${horas}=    Evaluate    (time.time() - ${inicio}) / 3600
    Set To Dictionary    ${amostra}    horas=${horas}    evento=${evento}
    Gravar Csv    ${tipo}    &{amostra}
    RETURN    ${amostra}

Validar limite máximo
    [Documentation]    Falha se a métrica passar do limite. Grava medida e limite no log.
    [Arguments]    ${nome}    ${valor}    ${limite}
    ${valor}=    Convert To Number    ${valor}
    Log    ${nome}: ${valor} (limite ${limite})    console=True
    IF    ${valor} > ${limite}
        Fail    ${nome} = ${valor}, acima do limite de ${limite}
    END

App não deve ter caído
    [Documentation]    Sem crash novo no logcat e com o mesmo processo.
    [Arguments]    ${pid_esperado}    ${crashes_antes}
    ${crashes}=    Contar Crashes    ${PACOTE}
    Should Be Equal As Integers    ${crashes}    ${crashes_antes}    O app registrou um crash no logcat.
    ${pid}=    Obter Pid    ${PACOTE}
    Should Be Equal As Integers    ${pid}    ${pid_esperado}    O processo do app morreu ou reiniciou.

App deve continuar vivo
    [Documentation]    Não caiu e segue em primeiro plano.
    [Arguments]    ${pid_esperado}    ${crashes_antes}
    App não deve ter caído    ${pid_esperado}    ${crashes_antes}
    ${foco}=    Obter Pacote Em Foco
    Should Be Equal    ${foco}    ${PACOTE}    O app saiu do primeiro plano.

Esperar mantendo a sessão
    [Documentation]    Espera longa sem estourar o newCommandTimeout de 240 s da sessão.
    [Arguments]    ${segundos}
    ${restante}=    Convert To Number    ${segundos}
    WHILE    ${restante} > 0    limit=NONE
        ${passo}=    Evaluate    min(60, ${restante})
        Sleep    ${passo}
        Adb Shell    true
        ${restante}=    Evaluate    ${restante} - ${passo}
    END

Rolar a tela
    [Documentation]    Arrasta no meio da tela. direcao=1 sobe a lista, direcao=-1 desce.
    [Arguments]    ${direcao}=1    ${duracao}=0.3
    ${largura}=    Get Window Width
    ${altura}=    Get Window Height
    ${x}=    Evaluate    int(${largura} / 2)
    ${y1}=    Evaluate    int(${altura} * (0.5 + 0.3 * ${direcao}))
    ${y2}=    Evaluate    int(${altura} * (0.5 - 0.3 * ${direcao}))
    Arrastar    ${x}    ${y1}    ${x}    ${y2}    ${duracao}
