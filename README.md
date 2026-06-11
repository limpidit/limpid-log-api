# Limpid IT — Log Console API

API FastAPI pour la réception **en temps réel** et la consultation des logs EBP.

Au lieu d'écrire dans un fichier .txt local, le code EBP appelle directement cette API
à chaque ligne de log.

## Démarrage local

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # éditer avec vos variables
uvicorn app.main:app --reload
python seed.py        # créer le 1er compte + clé API
```

## Endpoints de push (depuis le code EBP)

### Une ligne à la fois
```http
POST /api/log
X-API-Key: llk_votre_cle

{
  "api_code": "LITPRX",
  "level": "error",
  "message": "Avenants Manquants - produit bloqué #23560",
  "logged_at": "2026-05-26T18:28:05",
  "run_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Levels :** `info` | `warning` | `error` | `system`

**run_id :** UUID généré une fois au démarrage de l'exécution, permet de regrouper
tous les logs d'une même session. Optionnel.

### Batch (flush d'un buffer)
```http
POST /api/logs/batch
X-API-Key: llk_votre_cle

{
  "run_id": "550e8400-...",
  "entries": [
    { "api_code": "LITPRX", "level": "info", "message": "Démarrage" },
    { "api_code": "LITPRX", "level": "error", "message": "Erreur X" }
  ]
}
```

## Exemple d'intégration C# / .NET (EBP)

```csharp
// Au démarrage de l'exécution
var runId = Guid.NewGuid().ToString();
var httpClient = new HttpClient();
httpClient.DefaultRequestHeaders.Add("X-API-Key", "llk_votre_cle");

// À chaque log
async Task Log(string apiCode, string level, string message)
{
    var payload = new {
        api_code = apiCode,
        level = level,           // "info" | "warning" | "error" | "system"
        message = message,
        logged_at = DateTime.UtcNow,
        run_id = runId
    };
    await httpClient.PostAsJsonAsync("https://limpid-log-api.onrender.com/api/log", payload);
}

// Utilisation
await Log("LITPRX", "info", "Démarrage synchronisation Praxedo");
await Log("LITPRX", "error", "Avenants Manquants - produit bloqué");
await Log("LITPRX", "info", "Fin de traitement");
```

## Endpoints de lecture (console web — JWT requis)

- `GET /api/dashboard` — stats du jour + dernières erreurs
- `GET /api/logs?client_id=&level=&api_code=&search=&page=` — logs filtrés
- `GET /api/logs/sessions` — sessions d'exécution
- `GET /api/clients` — clients avec stats
- `GET/POST /api/admin/clients` — gestion clients
- `GET/POST/DELETE /api/admin/api-keys` — clés API
- `GET/POST /api/admin/users` — utilisateurs Limpid IT
