# MyActuator Web Dashboard

Prototype browser dashboard for exercising the repository's internal 64-byte
frame and a synthetic motor model. It is not the authoritative MYACTUATOR
protocol simulator and is not approved for powered-hardware control.

It is a pure front-end (ES modules, no build step) that mirrors the host-side
Python protocol library (`host/myactuator_lib/`) and the firmware contracts in
`contracts/`.

## Layout

| Path | What it is |
|------|------------|
| `index.html` | Dashboard shell (fleet / detail / event log). |
| `css/style.css` | Dark control-room theme. |
| `js/protocol.js` | Faithful JS port of the 64-byte unified frame + CRC-16/CCITT-FALSE. |
| `js/motors.js` | Motor catalog from the per-series contracts + model-number decoder. |
| `js/sim.js` | In-browser motor simulation (physics + fault injection + status frames). |
| `js/webserial.js` | WebSerial transport (connect/send/receive 64-byte frames). |
| `js/app.js` | Dashboard controller wiring the above to the DOM. |
| `test/*.mjs` | Node verification of protocol + sim. |
| `serve.py` | Tiny static server (WebSerial needs a secure context; localhost qualifies). |

## Run it

```bash
cd /home/roko/Documents/Projects/myactuator
python3 web/serve.py 8000
# open http://localhost:8000 in Chrome/Edge
```

Click **Start Simulation** to spin up a 6-motor fleet (one per series) and
watch live position/velocity/torque/temperature. Select a motor, enable it,
pick a control mode (position / velocity / torque), and send setpoints. The
**Overheat** button injects a thermal fault to exercise the fault path.

## Experimental WebSerial path

The UI can open an ESP32 USB CDC port and exchange the repository's internal
64-byte prototype frames. This is not MYACTUATOR native CAN framing. The
current serial/controller/driver path has not demonstrated real TX/RX,
feedback, command leases, physical stop or fault behavior, and it is not wired
through the canonical V4.4 codec and safety core. Do not use this path on a
powered actuator.

## Verify

```bash
cd web
npm test
```

The protocol test cross-checks the JS CRC-16/CCITT against the Python host
library (`host/myactuator_lib/protocol/frame.py`) so the two legacy prototype
paths stay in lockstep. These tests provide no rigid-body, plant or hardware
evidence.
