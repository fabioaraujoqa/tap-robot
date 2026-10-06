"""Exemplo: um teste Appium em que element.click() vira um toque físico do robô.

Rode da raiz do projeto:  python examples/appium_example.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from appium import webdriver
from appium.options.android import UiAutomator2Options
from appium.webdriver.common.appiumby import AppiumBy

from taprobot import BambuLink, Calibration, RobotTap, load_config
from taprobot.appium_patch import check_screen, physical_clicks

cfg = load_config("config.yaml")
cal = Calibration.load(cfg["calibration_file"])
p = cfg["printer"]
link = BambuLink(p["ip"], p["serial"], p["access_code"])
link.connect()
robot = RobotTap(cfg, link, cal)

options = UiAutomator2Options()
options.platform_name = "Android"
options.udid = "SEU_UDID"  # adb devices
options.app_package = "com.android.settings"
options.app_activity = ".Settings"
options.no_reset = True

driver = webdriver.Remote("http://127.0.0.1:4723", options=options)
try:
    check_screen(driver, cal)

    # Tudo dentro do bloco usa toque FÍSICO no lugar do click() do Appium.
    with physical_clicks(robot):
        item = driver.find_element(AppiumBy.XPATH, "(//android.widget.TextView)[1]")  # troque pelo seu
        item.click()

    # Gestos que o Appium faria por software viram movimentos do robô:
    robot.swipe_px(360, 1200, 360, 500, duration_s=0.4)  # rolar para baixo
    robot.long_press_px(360, 800, seconds=1.0)

    # O Appium continua cuidando de localizar elementos, esperar e validar:
    assert driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.TextView")
finally:
    driver.quit()
    robot.park()
    robot.link.close()
