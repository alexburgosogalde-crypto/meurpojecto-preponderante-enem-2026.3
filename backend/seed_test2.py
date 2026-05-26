"""Seed extra: +15 candidatos que salvam dados, fazem inscrição e SÓ geram PIX."""
import asyncio
import random
import httpx

API = "http://localhost:8001/api/donas"

NOMES = [
    "Roberta Aguiar", "Tiago Bittencourt", "Camila Vasconcelos", "Murilo Faria", "Letícia Bandeira",
    "Cauã Rezende", "Heloísa Drummond", "Augusto Coutinho", "Manuela Sampaio", "Otávio Maciel",
    "Yasmin Quintanilha", "Renan Bezerra", "Eduarda Galvão", "Hugo Pacheco", "Sophia Vilela",
]

CARGOS_MEDIO = [
    "Técnico em Infraestrutura e Manutenção – Edificações",
    "Técnico em Infraestrutura e Manutenção – Eletrotécnica",
    "Profissional Técnico de Navegação Aérea",
]
CARGOS_SUPERIOR = [
    "Analista Administrativo (Superior)",
    "Engenheiro Civil (Superior)",
    "Pedagogo (Superior)",
]

DOMINIOS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com.br"]


def gen_cpf(seed):
    return f"{random.randint(100,999):03d}{random.randint(100,999):03d}{random.randint(100,999):03d}{seed:02d}"[:11]


async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        # Desativa Telegram pra não floodar
        await client.put(f"{API}/config", json={"tgEnabled": False})
        print("Telegram desativado.")

        criadas = 0
        for i, nome in enumerate(NOMES, start=200):
            primeiro = nome.split()[0].lower()
            cpf = gen_cpf(i)
            email = f"{primeiro}{random.randint(10,999)}@{random.choice(DOMINIOS)}"
            senha = f"{primeiro.capitalize()}@{random.randint(1000,9999)}"

            # 1. Cadastro
            await client.post(f"{API}/cadastros", json={
                "cpf": cpf, "nome": nome.upper(), "email": email, "senha": senha,
                "telefone": f"({random.randint(11,99)}) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                "cidade": random.choice(["Niterói","Campinas","Recife","Porto Alegre","Goiânia","Manaus"]),
                "uf": random.choice(["RJ","SP","PE","RS","GO","AM"]),
            })

            # 2. Inscrição
            cargo = random.choice(CARGOS_MEDIO + CARGOS_SUPERIOR)
            r = await client.post(f"{API}/inscricoes", json={
                "cpf": cpf, "candidato": nome.upper(), "email": email, "cargo": cargo,
                "dispositivo": random.choice(["Desktop","Mobile"]),
            })
            if r.status_code != 200:
                continue
            insc_id = r.json()["id"]

            # 3. Só PIX gerado (nada de copiado/baixado)
            await client.patch(f"{API}/inscricoes/{insc_id}", json={"status": "PIX gerado"})
            criadas += 1

        # Reativa Telegram
        await client.put(f"{API}/config", json={"tgEnabled": True})
        print("Telegram reativado.")

        print(f"\nNovos candidatos criados (cadastro + inscrição + PIX gerado apenas): {criadas}/15")
        s = (await client.get(f"{API}/stats")).json()
        print("Stats acumuladas:", s)


if __name__ == "__main__":
    asyncio.run(main())
