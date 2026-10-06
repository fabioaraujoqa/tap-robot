"""Integração com o Appium: faz `element.click()` virar um toque físico do robô."""
from __future__ import annotations

import logging
from contextlib import contextmanager

log = logging.getLogger("taprobot.appium")


def element_center(element):
    r = element.rect
    return r["x"] + r["width"] / 2, r["y"] + r["height"] / 2


def check_screen(driver, calibration, tolerance=0.03):
    """Avisa se o tamanho da tela no Appium não bate com o da calibração."""
    size = driver.get_window_size()
    w, h = size["width"], size["height"]
    if (
        abs(w - calibration.screen_w) > tolerance * calibration.screen_w
        or abs(h - calibration.screen_h) > tolerance * calibration.screen_h
    ):
        log.warning(
            "tamanho da tela no Appium (%sx%s) difere da calibração (%sx%s): "
            "recalibre se mudou a resolução/escala de exibição",
            w, h, calibration.screen_w, calibration.screen_h,
        )


def install_physical_clicks(robot):
    """Troca WebElement.click por um toque do robô. Devolve a função que desfaz."""
    from appium.webdriver.webelement import WebElement

    original = WebElement.click

    def robot_click(self):
        x, y = element_center(self)
        log.info("toque físico em (%.0f, %.0f) px", x, y)
        robot.tap_px(x, y)

    WebElement.click = robot_click

    def restore():
        WebElement.click = original

    return restore


@contextmanager
def physical_clicks(robot):
    restore = install_physical_clicks(robot)
    try:
        yield
    finally:
        restore()
