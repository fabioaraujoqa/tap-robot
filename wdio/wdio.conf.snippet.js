// Trechos para o seu wdio.conf.js. Com ROBOT=1, todo element.click() vira um toque físico.
// Sem ROBOT, os testes rodam normalmente (clique por software do Appium).
//
//   Terminal 1:  python server.py
//   Terminal 2:  ROBOT=1 npx wdio run wdio.conf.js

const { RobotClient } = require('./wdio/robot-client');

const robot = new RobotClient();
const useRobot = !!process.env.ROBOT;

exports.config = {
  // ... o resto da sua configuração ...

  before: async function () {
    if (!useRobot) return;

    // Falha cedo e com mensagem clara se o servidor não estiver no ar ou sem calibração.
    const status = await robot.health();
    if (!status.calibrated) throw new Error('robô sem calibração: rode python calibrate.py run');

    // click() de elemento -> toque físico no centro do elemento.
    browser.overwriteCommand(
      'click',
      async function (originalClick) {
        const { x, y } = await this.getLocation();
        const { width, height } = await this.getSize();
        await robot.tap(x + width / 2, y + height / 2);
      },
      true, // comando de elemento
    );

    // Gestos físicos para usar nos testes: await browser.robotSwipe(360, 1200, 360, 500)
    browser.addCommand('robotSwipe', (x1, y1, x2, y2, durationS) => robot.swipe(x1, y1, x2, y2, durationS));
    browser.addCommand('robotLongPress', (x, y, seconds) => robot.longPress(x, y, seconds));
  },

  after: async function () {
    if (useRobot) await robot.park();
  },
};
