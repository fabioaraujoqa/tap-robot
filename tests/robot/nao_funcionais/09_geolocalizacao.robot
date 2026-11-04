*** Settings ***
Documentation     Rota simulada, salto brusco e GPS desligado.
...
...               O ApiDemos não tem tela de GPS, então nada aqui valida o app usando a posição.
...               O teste confere o que o aparelho informa e que o app sobrevive às mudanças.
...               No aparelho real, o Appium Settings precisa da permissão de localização.
Resource          resources/nfr_keywords.resource
Suite Setup       Abrir sessão NFR    .view.List1
Suite Teardown    Encerrar geolocalização
Test Tags         emulador    aparelho_real


*** Test Cases ***
Rota simulada é seguida pelo aparelho
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    FOR    ${latitude}    ${longitude}    IN
    ...    -23.5505    -46.6333
    ...    -23.5510    -46.6340
    ...    -23.5515    -46.6347
    ...    -23.5520    -46.6354
        Ir para a posição    rota    ${latitude}    ${longitude}
    END
    App deve continuar vivo    ${pid}    ${crashes}

Salto brusco de posição não derruba o app
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    Ir para a posição    salto    -23.5505    -46.6333
    Ir para a posição    salto    48.8566    2.3522
    App deve continuar vivo    ${pid}    ${crashes}

GPS desligado não derruba o app
    [Teardown]    Adb Shell    cmd location set-location-enabled true
    ${pid}=    Obter Pid    ${PACOTE}
    ${crashes}=    Contar Crashes    ${PACOTE}
    Adb Shell    cmd location set-location-enabled false
    Sleep    2s
    ${estado}=    Adb Shell    cmd location is-location-enabled
    Should Contain    ${estado}    false    O aparelho não desligou a localização.
    # ao desligar o GPS, às vezes o Google Play Services abre um diálogo sobre o app; isso não é falha
    App não deve ter caído    ${pid}    ${crashes}
    ${foco}=    Obter Pacote Em Foco
    IF    $foco != $PACOTE
        Log    ${foco} está na frente do app depois de desligar o GPS.    WARN
    END


*** Keywords ***
Ir para a posição
    [Arguments]    ${caso}    ${latitude}    ${longitude}
    Set Geolocation    ${latitude}    ${longitude}
    # o Appium Settings recebe o GPS a cada 60 s, então a posição nova pode demorar a aparecer
    ${lida}=    Wait Until Keyword Succeeds    75s    3s    Aparelho deve estar em    ${latitude}    ${longitude}
    Gravar Csv    geolocalizacao    caso=${caso}    latitude=${latitude}    longitude=${longitude}
    ...    latitude_lida=${lida}[latitude]    longitude_lida=${lida}[longitude]

Aparelho deve estar em
    [Arguments]    ${latitude}    ${longitude}
    ${lida}=    Obter Ultima Posicao
    Should Be True    abs(${lida}[latitude] - ${latitude}) < 0.01    O aparelho informou outra latitude: ${lida}
    Should Be True    abs(${lida}[longitude] - ${longitude}) < 0.01    O aparelho informou outra longitude: ${lida}
    RETURN    ${lida}

Encerrar geolocalização
    Run Keyword And Ignore Error    Reset Geolocation
    Fechar sessão NFR
