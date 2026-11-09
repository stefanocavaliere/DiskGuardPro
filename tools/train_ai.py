"""Ri-allena il modello AI di DiskGuard Pro su CSV stile Backblaze.
Uso:  python tools/train_ai.py dati_2024.csv
Il CSV deve contenere almeno: smart_5_raw,smart_197_raw,smart_198_raw,
smart_194_raw,smart_9_raw,failure (1=guasto). Colonne extra benvenute.
Scrive core/ai_weights.json (usato automaticamente dall'app).
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.ai import retrain_from_csv

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    r = retrain_from_csv(sys.argv[1])
    print(r)
