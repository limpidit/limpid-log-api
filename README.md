# Limpid IT — Log Console API

API FastAPI pour la réception et la consultation des logs EBP des développements Limpid IT.

## Démarrage local

```bash
# Créer un virtualenv
python -m venv .venv
source .venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Configurer
cp .env.example .env
# Éditer .env avec vos variables

# Lancer (auto-crée les tables au démarrage)
uvicorn app.main:app --reload

# Créer le premier utilisateur + client de test
python seed.py
```

## Endpoints principaux

### Auth (console web)
- `POST /api/auth/login` — `{email, password}` → `{access_token, refresh_token}`
- `POST /api/auth/refresh` — `{refresh_token}` → nouveaux tokens

### Push logs (depuis EBP)
- `POST /api/push/logs` — multipart avec `file` + header `X-API-Key`
- `POST /api/push/logs/raw?filename=LogXXX.txt` — corps texte brut + header `X-API-Key`

### Console (authentifié JWT)
- `GET /api/dashboard` — stats du jour + dernières erreurs
- `GET /api/logs?client_id=&level=&api_code=&search=&page=&page_size=` — logs filtrés
- `GET /api/logs/sessions` — fichiers reçus
- `GET /api/clients` — clients avec stats

### Admin (authentifié JWT)
- `GET/POST /api/admin/clients` — gestion clients
- `GET/POST/DELETE /api/admin/api-keys` — gestion clés API
- `GET/POST /api/admin/users` — gestion utilisateurs

## Format de log attendu

```
API LITPRX - 26/05/2026 18:19:05 : Dernier Fichier de log bien envoyé
API LITGAF - 26/05/2026 18:22:52 : DBName - T2M_xxx - API Name Extension GAFIC - DBId : uuid - user EBPSDK
API LITPRX - 26/05/2026 18:28:05 : ERREUR !! : Message d'erreur
API LITGAF - 26/05/2026 18:28:05 : WARNING : Message warning
API LITGAF - 26/05/2026 18:28:05 : info : Message informatif
```

## Exemple d'intégration EBP (PowerShell)

```powershell
$apiKey = "llk_votre_cle_api"
$logFile = "C:\EBP\Logs\LogT2M_uuid.txt"
$apiUrl = "https://limpid-log-api.onrender.com/api/push/logs"

$form = @{ file = Get-Item $logFile }
Invoke-RestMethod -Uri $apiUrl -Method POST -Form $form -Headers @{ "X-API-Key" = $apiKey }
```
