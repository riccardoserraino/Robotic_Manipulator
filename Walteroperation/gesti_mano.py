"""
gesti_mano.py - Riconoscimento dei gesti della mano per la teleoperazione.

Trasforma i 21 punti di MediaPipe (vedi hand_webcam.py) in una parola del
protocollo del robot:

    solo indice verso SINISTRA  -> "left"
    solo indice verso DESTRA    -> "right"
    solo indice verso l'ALTO    -> "up"
    solo indice verso il BASSO  -> "down"
    pollice in SU (pugno)       -> "forward"
    pollice in GIU' (pugno)     -> "backward"
    qualsiasi altra cosa        -> "stop"   (nessuna mano, mano aperta, gesto incerto)

Sinistra/destra sono quelle dell'immagine SPECCHIATA (come in hand_webcam.py):
muovi la mano come davanti a uno specchio. Se, da dove stai, la direzione
del robot risulta invertita, cambia GESTO_A_COMANDO (non il programma robot).

Due parti:
  classifica(landmarks)  -> gesto del singolo fotogramma
  Stabilizzatore         -> evita sfarfallii: un gesto nuovo diventa attivo dopo
                            N_CONFERMA fotogrammi uguali; lo stop arriva dopo
                            T_PERDITA_S senza un gesto valido.

Uso da solo (taratura dei gesti, senza robot):
    python gesti_mano.py
    python gesti_mano.py --camera 1
Q / ESC per uscire.
"""

import math

# --------------------------------------------------------------------------------------
# Parametri da tarare
# --------------------------------------------------------------------------------------

# Gesto riconosciuto -> parola mandata al robot. Cambiare qui se la direzione
# del robot non corrisponde a quella del gesto da dove sta l'operatore.
GESTO_A_COMANDO = {
    "indice_sx": "left",
    "indice_dx": "right",
    "indice_su": "up",
    "indice_giu": "down",
    "pollice_su": "forward",
    "pollice_giu": "backward",
}

ANGOLO_MAX_DEG = 35.0     # tolleranza attorno a orizzontale/verticale; fuori = gesto incerto
LUNGHEZZA_MIN = 0.45      # dito puntato: lunghezza minima (rispetto al palmo) nel piano immagine;
                          # piu' corto = dito verso la camera = gesto incerto
N_CONFERMA = 3            # fotogrammi uguali consecutivi per attivare un gesto nuovo (~0.1 s a 30 fps)
T_PERDITA_S = 0.15        # senza gesto valido per questo tempo -> stop

# Indici dei landmark MediaPipe
POLSO = 0
POLLICE = (1, 2, 3, 4)        # CMC, MCP, IP, punta
INDICE = (5, 6, 7, 8)         # MCP, PIP, DIP, punta
MEDIO = (9, 10, 11, 12)
ANULARE = (13, 14, 15, 16)
MIGNOLO = (17, 18, 19, 20)


# --------------------------------------------------------------------------------------
# Classificazione di un singolo fotogramma
# --------------------------------------------------------------------------------------

def _xy(lm):
    return lm.x, lm.y


def _dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def dito_teso(lm, dito):
    """Dito (non pollice) teso: la punta e' piu' lontana dal polso della nocca centrale (PIP)."""
    mcp, pip, dip, punta = (lm[i] for i in dito)
    return _dist(lm[POLSO], punta) > _dist(lm[POLSO], pip) * 1.15


def dito_piegato(lm, dito):
    """Dito (non pollice) chiuso: la punta e' piu' vicina al polso della nocca centrale."""
    mcp, pip, dip, punta = (lm[i] for i in dito)
    return _dist(lm[POLSO], punta) < _dist(lm[POLSO], pip) * 1.05


def pollice_teso(lm, palmo):
    """Pollice aperto: la punta e' lontana dalla base dell'indice."""
    return _dist(lm[POLLICE[3]], lm[INDICE[0]]) > 0.55 * palmo


def direzione(da, a, palmo):
    """Direzione dominante del vettore da->a nell'immagine: 'sx', 'dx', 'su', 'giu' o None.

    None se il vettore e' troppo corto (dito verso la camera) o troppo obliquo.
    Ricorda: nell'immagine y cresce verso il BASSO.
    """
    vx, vy = a.x - da.x, a.y - da.y
    lunghezza = math.hypot(vx, vy)
    if lunghezza < LUNGHEZZA_MIN * palmo:
        return None
    angolo = math.degrees(math.atan2(-vy, vx))   # 0 = destra, 90 = su, 180 = sinistra, -90 = giu'
    for nome, centro in (("dx", 0.0), ("su", 90.0), ("sx", 180.0), ("giu", -90.0)):
        scarto = abs((angolo - centro + 180.0) % 360.0 - 180.0)
        if scarto <= ANGOLO_MAX_DEG:
            return nome
    return None


def classifica(lm):
    """Gesto di un fotogramma ('indice_sx', 'pollice_su', ...) oppure None.

    lm: lista dei 21 landmark di UNA mano (oggetti con .x e .y normalizzati 0..1).
    """
    palmo = _dist(lm[POLSO], lm[MEDIO[0]])   # polso -> base del medio: scala della mano
    if palmo < 1e-6:
        return None
    altri_chiusi = all(dito_piegato(lm, d) for d in (MEDIO, ANULARE, MIGNOLO))
    if not altri_chiusi:
        return None   # mano aperta o dita a caso: nessun comando

    # Solo indice teso (il pollice puo' essere come capita)
    if dito_teso(lm, INDICE):
        verso = direzione(lm[INDICE[0]], lm[INDICE[3]], palmo)
        return f"indice_{verso}" if verso else None

    # Pugno con pollice teso: su o giu'
    if dito_piegato(lm, INDICE) and pollice_teso(lm, palmo):
        verso = direzione(lm[POLLICE[1]], lm[POLLICE[3]], palmo)
        if verso in ("su", "giu"):
            return f"pollice_{verso}"
    return None


def comando_da_risultato(result):
    """Parola per il robot dal risultato di MediaPipe (prima mano trovata), 'stop' se niente."""
    if not result.hand_landmarks:
        return "stop", None
    gesto = classifica(result.hand_landmarks[0])
    return GESTO_A_COMANDO.get(gesto, "stop"), gesto


# --------------------------------------------------------------------------------------
# Stabilizzazione nel tempo
# --------------------------------------------------------------------------------------

class Stabilizzatore:
    """Filtra il comando grezzo di ogni fotogramma.

    - Un comando di moto nuovo diventa attivo solo dopo N_CONFERMA fotogrammi uguali.
    - Lo stop arriva dopo T_PERDITA_S senza il comando attivo (un fotogramma perso
      non ferma il robot, ma il ritardo resta piccolo).
    """

    def __init__(self, n_conferma=N_CONFERMA, t_perdita=T_PERDITA_S):
        self.n_conferma = n_conferma
        self.t_perdita = t_perdita
        self.attivo = "stop"
        self._candidato = None
        self._conta = 0
        self._ultimo_visto = 0.0

    def aggiorna(self, grezzo, adesso):
        """Riceve il comando grezzo del fotogramma, restituisce il comando stabile."""
        if grezzo == self.attivo and grezzo != "stop":
            self._ultimo_visto = adesso
            self._candidato, self._conta = None, 0
            return self.attivo

        if grezzo != "stop":
            if grezzo == self._candidato:
                self._conta += 1
            else:
                self._candidato, self._conta = grezzo, 1
            if self._conta >= self.n_conferma:
                self.attivo = grezzo
                self._ultimo_visto = adesso
                self._candidato, self._conta = None, 0
                return self.attivo
        else:
            self._candidato, self._conta = None, 0

        # Nessuna conferma del comando attivo in questo fotogramma
        if self.attivo != "stop" and adesso - self._ultimo_visto >= self.t_perdita:
            self.attivo = "stop"
        return self.attivo


# --------------------------------------------------------------------------------------
# Disegno e uso da solo (taratura)
# --------------------------------------------------------------------------------------

def scrivi_stato(frame, gesto, grezzo, stabile, fps=None):
    """Scrive in alto nell'immagine gesto riconosciuto e comando stabile."""
    import cv2
    colore = (0, 200, 0) if stabile != "stop" else (0, 0, 255)
    cv2.putText(frame, f"CMD: {stabile}", (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 1.1, colore, 3)
    testo = f"gesto: {gesto or '-'}  grezzo: {grezzo}"
    if fps is not None:
        testo += f"  FPS {fps:.0f}"
    cv2.putText(frame, testo, (10, 65), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)


def main():
    import argparse
    import time

    import cv2
    import mediapipe as mp

    from hand_webcam import create_detector, draw_hands

    ap = argparse.ArgumentParser(description="Taratura dei gesti (senza robot)")
    ap.add_argument("--camera", type=int, default=0, help="indice della webcam")
    args = ap.parse_args()

    cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
    if not cap.isOpened():
        raise SystemExit(f"Impossibile aprire la webcam {args.camera}")
    stab = Stabilizzatore()
    t0 = time.monotonic()
    t_prec = t0
    ultimo = None
    with create_detector(1) as detector:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame = cv2.flip(frame, 1)
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            adesso = time.monotonic()
            result = detector.detect_for_video(
                mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int((adesso - t0) * 1000))
            grezzo, gesto = comando_da_risultato(result)
            stabile = stab.aggiorna(grezzo, adesso)
            if stabile != ultimo:
                print(f"comando: {stabile}")
                ultimo = stabile
            draw_hands(frame, result)
            fps = 1.0 / max(adesso - t_prec, 1e-6)
            t_prec = adesso
            scrivi_stato(frame, gesto, grezzo, stabile, fps)
            cv2.imshow("Gesti - taratura (Q per uscire)", frame)
            if cv2.waitKey(1) & 0xFF in (ord("q"), 27):
                break
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
