# HelloWorld Android avec Python et Kivy

Ce petit projet permet de lancer une application Kivy sur l'ordinateur, de
générer son APK Android avec Buildozer, puis de transférer cet APK sur un
téléphone connecté en USB. Le premier build télécharge Android SDK/NDK et les
outils de compilation ; il peut prendre un moment.

## 1. Préparer Ubuntu

Buildozer cible Linux. Dans un terminal, installe les outils système requis :

```bash
sudo apt update
sudo apt install -y \
  autoconf automake build-essential cmake git libffi-dev libltdl-dev libtool \
  libncurses5-dev libncursesw5-dev libssl-dev openjdk-17-jdk \
  pkg-config python3-dev python3-venv unzip zip zlib1g-dev adb
```

Le dossier de travail doit être sur un système de fichiers Linux local avec
prise en charge des liens symboliques. Si le projet est sur un disque partagé
ou monté (`/media/...`), copie-le dans ton dossier Linux, par exemple
`~/Android/helloworld`, avant le build :

```bash
mkdir -p ~/Android/helloworld
cp -a main.py buildozer.spec requirements-dev.txt README.md ~/Android/helloworld/
cp -a .vscode ~/Android/helloworld/
cd ~/Android/helloworld
```

## 2. Installer l'environnement Python du projet

Depuis le dossier du projet :

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements-dev.txt
```

Dans VS Code, ouvre ce dossier et sélectionne l'interpréteur
`.venv/bin/python` si VS Code ne l'a pas choisi automatiquement. Les tâches
Kivy et Android sont disponibles avec **Terminal > Run Task**.

## 3. Essayer sur l'ordinateur

```bash
source .venv/bin/activate
python main.py
```

Ou lance la tâche VS Code **Kivy: run on desktop**.

## 4. Générer l'APK Android

```bash
source .venv/bin/activate
buildozer android debug
```

Accepte les licences Android si demandé. Le premier build configure
automatiquement le SDK et le NDK dans `.buildozer/`. L'APK de test est créé
dans `bin/` (nommé `helloworld-0.1.0-arm64-v8a-debug.apk`).

La tâche VS Code **Android: build debug APK** lance la même commande. Pour
obtenir un APK installable sur des téléphones Android 64 bits ARM récents,
l'architecture `arm64-v8a` est configurée. L'APK `debug` est destiné aux
tests, pas à une publication sur un magasin.

### Générer l'APK avec GitHub Actions

Le workflow `.github/workflows/android.yml` compile automatiquement un APK
à chaque `push` sur `main` ou `master`. Il peut aussi être lancé manuellement
depuis l'onglet **Actions** du dépôt GitHub avec **Run workflow**.
Le dépôt inclut une recette python-for-android locale pour `libthorvg`,
nécessaire avec le NDK 25b, qui range `libomp.so` sous `lib64/clang`.
Cette même recette est utilisée par le build local et par GitHub Actions.

Pour le premier envoi de ce dossier vers GitHub :

```bash
git add .github .gitignore .vscode README.md buildozer.spec main.py requirements-dev.txt
git commit -m "Add Kivy Android Hello World"
git push -u origin main
```

Si Git demande une identité avant le commit, configure ton nom et l'adresse
associée à ton compte GitHub dans VS Code ou dans un terminal :

```bash
git config --global user.name "Ton nom"
git config --global user.email "ton-adresse-associee-a-github@example.com"
```

À la première poussée, VS Code peut demander l'autorisation de se connecter à
GitHub. Une fois l'envoi terminé, chaque nouveau `push` sur `main` relance la
compilation.

Quand le build est terminé, ouvre son résultat dans **Actions**, puis
télécharge l'artefact **helloworld-debug-apk**. L'archive contient l'APK ;
transfère-le sur la tablette et ouvre-le pour l'installer. Les artefacts sont
conservés pendant 14 jours.

## 5. Installer et lancer sur le téléphone

1. Sur le téléphone, active les **Options pour les développeurs**, puis le
   **Débogage USB**.
2. Connecte-le en USB, déverrouille-le et autorise la clé de débogage de cet
   ordinateur.
3. Vérifie la connexion puis installe l'APK :

   ```bash
   adb devices
   adb install -r bin/helloworld-0.1.0-arm64-v8a-debug.apk
   ```

La tâche **Android: install APK on connected phone** construit puis installe
l'APK en une commande. Tu peux aussi copier l'APK depuis `bin/` sur le mobile
et l'ouvrir ; Android peut demander d'autoriser l'installation depuis cette
source.

## Dépannage

- **`adb` introuvable** : installe `adb` (`sudo apt install adb`) ou ajoute
  `platform-tools` du SDK Android au `PATH`.
- **Licence ou téléchargement SDK/NDK** : relance `buildozer android debug`
  dans un terminal et lis/valide les demandes affichées.
- **Échec lié au disque partagé** : réalise le build depuis une copie dans le
  système de fichiers Linux local, comme indiqué à l'étape 1.
- **`clang: error: unable to execute command: Bus error`** : si le build est
  lancé depuis `/media/psf`, le linker Android peut planter sur ce système de
  fichiers partagé, y compris pendant la compilation de dépendances comme
  libjpeg. Refais le build depuis une copie dans le système de fichiers Linux
  local, pas depuis `/media/psf`. Le même plantage peut aussi faire échouer le
  test `libm` de Python.
- **`remote_debugging.c: error: implicit declaration of function 'pwritev'`**
  : Python 3.14 nécessite Android API 24 au minimum pour cette fonction.
  `android.minapi = 24` est configuré dans `buildozer.spec`; envoie ce
  changement à GitHub pour relancer le build. Cela exclut uniquement les
  appareils antérieurs à Android 7.0 (Nougat).
- **Erreur pip SSL ou wheel Android non pris en charge** : la version
  précédente de python-for-android utilisait ici un installateur incompatible
  avec Python 3.14 et ses wheels Android. Le projet utilise maintenant la
  branche corrigée `develop`.
- **`libthorvg` échoue avec `IndexError` pendant la recherche de `libomp.so`**
  : vérifie que la recette du dépôt `p4a-recipes/libthorvg` est présente et
  que `p4a.local_recipes = p4a-recipes` figure dans `buildozer.spec`.
- **Repartir d'une compilation propre** : exécute
  `buildozer android clean`, puis relance le build.
