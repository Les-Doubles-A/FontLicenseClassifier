# FontCheck (outil original, fourni par l'utilisateur)

Copie de l'outil `FontCheck.py` original (navigateur local des polices
Windows installees, avec statut de licence par famille) fourni pour
integration. Non modifie.

Il lit/ecrit `%APPDATA%/FontCheck/licenses.json`. C'est exactement ce
fichier que `integrations/fontcheck_bridge.py` de FontLicenseClassifier met
a jour automatiquement a la fin de chaque analyse (voir le README principal,
section "Integration avec FontCheck") : lancez une analyse avec
FontLicenseClassifier, puis ouvrez `python FontCheck_tool/fontcheck.py`
pour voir les badges de licence deja renseignes.
