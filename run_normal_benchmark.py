"""
Raccourci pour le benchmark "normal" (mai 2023).
Équivalent à: python run_benchmark.py --mode normal
"""
from run_benchmark import main
import sys

if __name__ == "__main__":
    sys.argv = [sys.argv[0], "--mode", "normal"]
    main()
