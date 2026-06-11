"""
Seed script: creates the first admin user and optionally a test client + API key.
Run: python seed.py
"""
import asyncio
import os

from dotenv import load_dotenv

load_dotenv()

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password, generate_api_key, hash_api_key
from app.models.user import User
from app.models.client import Client
from app.models.api_key import ApiKey


async def main():
    async with AsyncSessionLocal() as db:
        # Create admin user
        email = input("Email admin [hubert.ouizille@limpidit.com]: ").strip() or "hubert.ouizille@limpidit.com"
        name = input("Nom admin [Hubert Ouizille]: ").strip() or "Hubert Ouizille"
        password = input("Mot de passe: ").strip()

        user = User(email=email, name=name, hashed_password=hash_password(password))
        db.add(user)
        await db.flush()
        print(f"✓ Utilisateur créé : {email}")

        # Optionally create a test client
        create_client = input("\nCréer un client de test ? (o/N): ").strip().lower()
        if create_client == "o":
            db_name = input("DBName du client [T2M]: ").strip() or "T2M"
            display = input(f"Nom d'affichage [{db_name}]: ").strip() or db_name

            client = Client(db_name=db_name, display_name=display)
            db.add(client)
            await db.flush()

            raw_key = generate_api_key()
            api_key = ApiKey(
                client_id=client.id,
                name=f"Clé API {db_name}",
                key_hash=hash_api_key(raw_key),
            )
            db.add(api_key)
            print(f"\n✓ Client créé : {db_name}")
            print(f"✓ Clé API (à sauvegarder) : {raw_key}")

        await db.commit()
        print("\n✓ Seed terminé !")


if __name__ == "__main__":
    asyncio.run(main())
