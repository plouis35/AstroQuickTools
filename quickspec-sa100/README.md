# QuickSpec SA100 — version Kivy

Ce sous-projet Android reste indépendant de QuickSpec PySide6. L’application
est organisée en un point d’entrée, une GUI et deux modules de traitement :

- `gui.py` — classe principale `QuickSpecGUI`, affichage Kivy, sélecteur PNG
  et orchestration.
- `image_processing.py` — classe `Image` : lecture PNG en tableaux NumPy,
  combinaison, corrections offset/dark/flat et registration subpixel.
- `spectra_processing.py` — classe `Spectra` : redressement, extraction avec
  soustraction du ciel et calibration linéaire SA100.
- `main.py` — lance l’application.

Le périmètre d’entrée est volontairement limité aux PNG. Les PNG couleur sont
convertis en niveaux de gris ; pour les mesures, privilégie des PNG gris sans
balance des blancs ni traitement d’image. Aucun en-tête d’exposition n’est
disponible dans ces fichiers : les darks ne sont donc pas mis à l’échelle par
temps de pose.

## Utiliser l’application

1. Dans l’onglet **Image**, ouvre un PNG.
2. Zoome avec le pincement à deux doigts ou les boutons **+** / **−** ;
   déplace l’image en la faisant glisser. **Ajuster** recentre l’image à sa
   taille initiale.
3. Choisis **Sélection SA100**.
4. Clique successivement l’ordre zéro, un point sur le spectre, puis un point
   dans la bande de ciel. Une croix rouge repère l’ordre zéro, verte la trace
   et bleue le fond de ciel ; les repères suivent l’image lors du zoom.
5. L’onglet **Spectre** s’ouvre avec le spectre extrait et calibré, gradué en
   longueur d’onde (Å) et en flux.

Le sélecteur rouvre le dernier dossier utilisé sur ordinateur et le dernier
emplacement de document Android lorsque le fournisseur de fichiers le permet.

Les paramètres optiques et de sélection sont pour l’instant des valeurs par
défaut dans `Spectra` (`distance_mm`, `pixel_size_um`, demi-hauteur des bandes
et limites de longueur d’onde).

## Environnement de développement

Depuis `quickspec-sa100/` dans la copie Linux locale :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python main.py
```

Les tests ciblés du moteur de traitement se lancent avec :

```bash
python -m unittest discover -v
```

## Construire l’APK

Depuis le dossier du projet et dans la copie Linux locale (pas depuis
`/media/...`) :

```bash
../.venv/bin/buildozer android debug
```

Le fichier `buildozer.spec` inclut NumPy et Pillow en plus de Kivy. NumPy et
Pillow sont compilés pour Android par python-for-android. La recette locale
`../p4a-recipes` du projet parent est requise pour le correctif NDK/libthorvg
et contient un correctif NumPy qui conserve les options Meson de
cross-compilation de cette version de python-for-android.

Les rotations et registrations sont volontairement implémentées avec NumPy
seul et une interpolation bilinéaire. Le build Android SciPy actuellement
disponible échoue sur l’incompatibilité de ses sources générées avec les API
NumPy de la version Android ; le garder hors de l’APK évite cette dépendance
native supplémentaire. Le NDK reste donc sur la version 25b déjà utilisée par
le projet parent.
