# Walteroperation — tracking della mano da webcam

Riconoscimento della mano in tempo reale da webcam con Google MediaPipe: base per la teleoperazione dell'ER4-550.

| File | Cosa fa |
|---|---|
| `hand_webcam.py` | Tracking della mano da webcam: disegna i 21 punti (polso, nocche, punte delle dita) e distingue mano destra/sinistra |
| `models/hand_landmarker.task` | Modello MediaPipe pre-addestrato (necessario, non cancellarlo) |
| `environment.yml` | Descrizione dell'ambiente conda |

## 1. Installare conda (una volta sola)

Basta **Miniconda** (più leggera di Anaconda; se hai già Anaconda va bene uguale, salta questo passo).

1. Scarica l'installer Windows 64-bit da <https://www.anaconda.com/download/success> (sezione *Miniconda*).
2. Installa con le opzioni di default ("Just Me"). **Non** serve spuntare "Add to PATH".
3. Dal menu Start apri **Anaconda Prompt** e verifica:
   ```bat
   conda --version
   ```

Tutti i comandi `conda` qui sotto vanno dati nell'**Anaconda Prompt** (oppure nel terminale di VS Code dopo `conda init`, vedi in fondo).

## 2. Creare l'ambiente (una volta sola)

```bat
cd percorso\di\Robotic_Manipulator\walteroperation
conda env create -f environment.yml
```

Crea un ambiente chiamato `walteroperation` con Python 3.12 e MediaPipe (scarica qualche centinaio di MB).

## 3. Usarlo (ogni volta)

```bat
conda activate walteroperation
cd percorso\di\Robotic_Manipulator\walteroperation
python hand_webcam.py              # webcam di default
python hand_webcam.py --camera 1   # webcam USB esterna
python hand_webcam.py --hands 1    # traccia una sola mano (un po' più veloce)
```

Si apre una finestra con lo scheletro della mano disegnato sopra il video; **Q** o **ESC** per chiudere.

Il prompt mostra `(walteroperation)` a sinistra quando l'ambiente è attivo. Per uscire: `conda deactivate`.

## 4. Comandi conda utili

| Comando | A cosa serve |
|---|---|
| `conda env list` | Elenca gli ambienti installati |
| `conda env update -f environment.yml --prune` | Allinea l'ambiente dopo che qualcuno ha modificato `environment.yml` |
| `pip install <pacchetto>` | Aggiunge un pacchetto (con l'ambiente attivo); poi **aggiungilo a `environment.yml`** e pusha |
| `conda env remove -n walteroperation` | Cancella l'ambiente (per ricrearlo da zero) |

## 5. VS Code

- `Ctrl+Shift+P` → **Python: Select Interpreter** → scegli `walteroperation`.
- Se il terminale di VS Code non riconosce `conda`, esegui una volta nell'Anaconda Prompt `conda init powershell` e riapri VS Code.

## Note

- La cartella dell'ambiente (`env/`) **non** si mette su git: è grande, contiene binari Windows e percorsi assoluti. Ognuno se la ricrea con `environment.yml`.
- Se la finestra resta nera, prova un altro indice con `--camera` o chiudi le altre app che usano la webcam (Teams, Zoom...).
