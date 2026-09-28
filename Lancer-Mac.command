#!/bin/bash
cd "$(dirname "$0")"
if command -v python3 >/dev/null 2>&1; then
  python3 maj_prix.py
else
  echo "Python 3 n'est pas installé. Une page va s'ouvrir pour le télécharger."
  open https://www.python.org/downloads/
fi
echo
read -n 1 -s -r -p "Appuie sur une touche pour fermer."
