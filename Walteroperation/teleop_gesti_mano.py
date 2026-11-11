"""
teleop_gesti_mano.py - Teleoperazione dell'Estun ER4-550 con i gesti della mano.

Un solo programma, due thread:
  - thread principale: webcam + MediaPipe + gesti_mano -> comando stabile
    (OpenCV vuole la finestra nel thread principale)
  - thread ServerRobot: risponde a ogni "REQ" del robot con il comando corrente

Il robot si muove finche' il gesto e' tenuto; senza mano o con un gesto incerto
risponde "stop". Gesti e taratura: vedi gesti_mano.py
(provali prima da soli con: python gesti_mano.py).

Lato robot: Teleop_Gesti.erp + Teleop_Comm.erp (porta 9500, IP del PC).

Uso (ambiente conda walteroperation):
    python teleop_gesti_mano.py
    python teleop_gesti_mano.py --camera 1 --log prova_gesti.csv
Tasti nella finestra video:
    Q / ESC  -> manda "quit" al robot (torna in home) e chiude
    O / C    -> apre / chiude la pinza (inviato una volta)
"""

import argparse
import codecs
import threading
import time

import cv2
import mediapipe as mp

from gesti_mano import Stabilizzatore, comando_da_risultato, scrivi_stato
from hand_webcam import create_detector, draw_hands
from server_robot import ServerRobot


class ComandoCondiviso:
    """Comando corrente scritto dal thread camera e letto dal thread server."""

    def __init__(self):
        self._lock = threading.Lock()
        self._parola = "stop"
        self._istante = time.monotonic()
        self._monouso = None   # "open"/"close" da mandare una sola volta

    def scrivi(self, parola):
        with self._lock:
            self._parola = parola
            self._istante = time.monotonic()

    def monouso(self, parola):
        with self._lock:
            self._monouso = parola

    def leggi(self):
        with self._lock:
            if self._monouso:
                parola, self._monouso = self._monouso, None
                return parola, time.monotonic()
            return self._parola, self._istante


def main():
    ap = argparse.ArgumentParser(description="Teleoperazione a gesti (Estun)")
    ap.add_argument("--camera", type=int, default=0, help="indice della webcam")
    ap.add_argument("--port", type=int, default=9500, help="porta TCP (I_Porta_PC sul robot)")
    ap.add_argument("--terminatore", default="", help='"", "\\r", "\\n" o "\\r\\n"')
    ap.add_argument("--log", default=None, help="CSV con una riga per ogni REQ")
    ap.add_argument("--verbose", action="store_true", help="stampa anche le REQ con stop")
    args = ap.parse_args()

    comando = ComandoCondiviso()
    server = ServerRobot(comando.leggi, porta=args.port,
                         terminatore=codecs.decode(args.terminatore, "unicode_escape"),
                         log=args.log, verbose=args.verbose)

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Impossibile aprire la webcam {args.camera}")
    server.avvia()

    stab = Stabilizzatore()
    t0 = t_prec = time.monotonic()
    ultimo = None
    in_chiusura = False
    try:
        with create_detector(1) as detector:
            while True:
                ok, frame = cap.read()
                if not ok:
                    print("Webcam: frame non letto, chiudo.")
                    break
                frame = cv2.flip(frame, 1)
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                adesso = time.monotonic()
                result = detector.detect_for_video(
                    mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int((adesso - t0) * 1000))

                grezzo, gesto = comando_da_risultato(result)
                stabile = "stop" if in_chiusura else stab.aggiorna(grezzo, adesso)
                comando.scrivi(stabile)
                if stabile != ultimo:
                    print(f"Comando: {stabile}")
                    ultimo = stabile

                draw_hands(frame, result)
                fps = 1.0 / max(adesso - t_prec, 1e-6)
                t_prec = adesso
                scrivi_stato(frame, gesto, grezzo, stabile, fps)
                stato_robot = "robot connesso" if server.connesso else "robot NON connesso"
                cv2.putText(frame, stato_robot, (10, frame.shape[0] - 15),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6,
                            (0, 200, 0) if server.connesso else (0, 0, 255), 2)
                cv2.imshow("Teleop gesti (Q = quit robot)", frame)

                tasto = cv2.waitKey(1) & 0xFF
                if tasto in (ord("q"), 27):
                    if not server.connesso:
                        break
                    if not in_chiusura:
                        print("Quit: mando 'quit' al robot e chiudo dopo la disconnessione.")
                        server.richiedi_quit()
                        in_chiusura = True
                elif tasto == ord("o"):
                    comando.monouso("open")
                elif tasto == ord("c"):
                    comando.monouso("close")
                if in_chiusura and server.terminato():
                    break
    except KeyboardInterrupt:
        print("Interrotto (Ctrl+C).")
    finally:
        comando.scrivi("stop")
        server.ferma()
        cap.release()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
