// Configuração do WebdriverIO para os testes Appium no Moto G06.
//
//   Terminal 1:  appium
//   Terminal 2:  npm run wdio                (clique por software, sem robô)
//
// Com o robô (todo element.click() vira toque físico):
//   Terminal 1:  appium
//   Terminal 2:  python server.py            (ou --dry-run, sem a impressora)
//   Terminal 3:  npm run wdio:robot
//
// Outro app: APP=addnumber npm run wdio   (padrão: apidemos)
// Celular: acha o moto g06 no USB ou na Depuração por Wi-Fi (IP:porta descoberto sozinho).
//          Outro aparelho: ANDROID_UDID=<serial ou IP:porta> npm run wdio

const path = require('path');
const { RobotClient } = require('./wdio/robot-client');
const { resolveUdid } = require('./wdio/adb-connect');

const robot = new RobotClient();
const useRobot = !!process.env.ROBOT;

// Apps de teste. Cada um roda só os specs dele.
const APPS = {
  apidemos: {
    specs: ['./specs/apidemos.spec.js'],
    capabilities: {
      'appium:app': path.resolve(__dirname, 'apps/ApiDemos-debug.apk'),
      'appium:appPackage': 'io.appium.android.apis',
      'appium:appActivity': '.ApiDemos',
    },
  },
  // BrowserStack "AddNumber" (apps/app-debug.apk). Mira o SDK 23 e o Android 15 recusa
  // instalar pelo Appium; instale uma vez à mão:
  //   adb install -r --bypass-low-target-sdk-block apps/app-debug.apk
  addnumber: {
    specs: ['./specs/addnumber.spec.js'],
    capabilities: {
      'appium:appPackage': 'com.browserstack.addnumber',
      'appium:appActivity': '.MainActivity',
    },
  },
};
const appName = process.env.APP || 'apidemos';
const app = APPS[appName];
if (!app) throw new Error(`APP desconhecido: ${appName} (opções: ${Object.keys(APPS).join(', ')})`);

const udid = process.env.ANDROID_UDID || resolveUdid();

exports.config = {
  runner: 'local',
  hostname: '127.0.0.1',
  port: 4723,

  specs: app.specs,
  maxInstances: 1, // um celular, um robô

  capabilities: [
    {
      platformName: 'Android',
      'appium:automationName': 'UiAutomator2',
      'appium:udid': udid,
      ...app.capabilities,
      'appium:autoGrantPermissions': true,
      'appium:newCommandTimeout': 240,
    },
  ],

  logLevel: 'warn',
  waitforTimeout: 10000,
  connectionRetryTimeout: 120000,
  connectionRetryCount: 1,

  framework: 'mocha',
  reporters: ['spec'],
  mochaOpts: {
    ui: 'bdd',
    timeout: 120000, // toques físicos levam ~1–2 s cada
  },

  before: async function () {
    if (!useRobot) return;

    // Falha cedo e com mensagem clara se o servidor não estiver no ar ou sem calibração.
    const status = await robot.health();
    if (!status.calibrated) throw new Error('robô sem calibração: rode python calibrate.py run');
    if (status.simulated) console.warn('[robô] modo simulado (dry-run): os toques não são reais');

    // click() de elemento -> toque físico no centro do elemento.
    // No modo simulado o toque não acontece, então também clica por software
    // para o teste seguir em frente (o servidor só registra o G-code).
    browser.overwriteCommand(
      'click',
      async function (originalClick) {
        const { x, y } = await this.getLocation();
        const { width, height } = await this.getSize();
        await robot.tap(x + width / 2, y + height / 2);
        if (status.simulated) await originalClick();
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
