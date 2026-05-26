"""Script de seed: cria 50 candidatos fictícios e simula o fluxo pedido."""
import asyncio
import random
import httpx

API = "http://localhost:8001/api/donas"

NOMES = [
    "Lucas Silva", "Mariana Souza", "Pedro Oliveira", "Ana Clara Lima", "João Santos",
    "Beatriz Costa", "Rafael Almeida", "Camila Ferreira", "Gabriel Rodrigues", "Fernanda Alves",
    "Bruno Carvalho", "Isabela Martins", "Thiago Pereira", "Larissa Ribeiro", "Felipe Gomes",
    "Juliana Barbosa", "Diego Araújo", "Patrícia Cardoso", "Vinícius Nunes", "Carolina Dias",
    "Matheus Cavalcanti", "Letícia Moreira", "Eduardo Pinto", "Amanda Castro", "André Mendes",
    "Vanessa Rocha", "Henrique Teixeira", "Tatiane Lopes", "Ricardo Vieira", "Renata Correia",
    "Marcelo Freitas", "Priscila Monteiro", "Daniel Borges", "Bianca Ramos", "Leonardo Sales",
    "Aline Campos", "Roberto Cunha", "Natália Pires", "Gustavo Andrade", "Cintia Fonseca",
    "Marcos Brito", "Sabrina Tavares", "Anderson Mota", "Luana Lacerda", "Cristiano Cardoso",
    "Débora Magalhães", "Wesley Reis", "Adriana Siqueira", "Igor Lemos", "Talita Vargas",
]

CARGOS_MEDIO = [
    "Técnico em Infraestrutura e Manutenção – Edificações",
    "Técnico em Infraestrutura e Manutenção – Eletrotécnica",
    "Técnico em Infraestrutura e Manutenção – Mecânica",
    "Profissional Técnico de Navegação Aérea",
]
CARGOS_SUPERIOR = [
    "Analista Administrativo (Superior)",
    "Pedagogo (Superior)",
    "Engenheiro Civil (Superior)",
    "Advogado (Superior)",
]

DOMINIOS = ["gmail.com", "outlook.com", "hotmail.com", "yahoo.com.br", "uol.com.br"]


def gen_cpf(i):
    base = f"{random.randint(100,999):03d}{random.randint(100,999):03d}{random.randint(100,999):03d}{i:02d}"
    return base[:11]


async def disable_tg(client):
    await client.put(f"{API}/config", json={"tgEnabled": False})


async def enable_tg(client):
    await client.put(f"{API}/config", json={"tgEnabled": True})


async def main():
    async with httpx.AsyncClient(timeout=15) as client:
        await disable_tg(client)
        print("Telegram desativado para o seed.")

        candidatos = []
        for i, nome in enumerate(NOMES):
            primeiro = nome.split()[0].lower()
            cpf = gen_cpf(i)
            email = f"{primeiro}{random.randint(10,999)}@{random.choice(DOMINIOS)}"
            senha = f"{primeiro.capitalize()}@{random.randint(1000,9999)}"
            payload = {
                "cpf": cpf, "nome": nome.upper(), "email": email, "senha": senha,
                "telefone": f"({random.randint(11,99)}) 9{random.randint(1000,9999)}-{random.randint(1000,9999)}",
                "cidade": random.choice(["Rio de Janeiro","São Paulo","Belo Horizonte","Salvador","Brasília","Curitiba","Fortaleza"]),
                "uf": random.choice(["RJ","SP","MG","BA","DF","PR","CE"]),
            }
            r = await client.post(f"{API}/cadastros", json=payload)
            if r.status_code == 200:
                candidatos.append({"cpf": cpf, "nome": nome.upper(), "email": email})
        print(f"Cadastros criados: {len(candidatos)}/50")

        # Embaralha. Primeiros 10 NÃO fazem inscrição. Restantes 40 fazem.
        random.shuffle(candidatos)
        sem_inscricao = candidatos[:10]
        com_inscricao = candidatos[10:50]
        print(f"  - Apenas cadastro: {len(sem_inscricao)}")
        print(f"  - Cadastro + inscrição: {len(com_inscricao)}")

        # Cria inscrição para 40
        inscritos = []
        for c in com_inscricao:
            cargo = random.choice(CARGOS_MEDIO + CARGOS_SUPERIOR)
            payload = {
                "cpf": c["cpf"], "candidato": c["nome"], "email": c["email"], "cargo": cargo,
                "dispositivo": random.choice(["Desktop","Mobile"]),
            }
            r = await client.post(f"{API}/inscricoes", json=payload)
            if r.status_code == 200:
                data = r.json()
                inscritos.append({"id": data["id"], "cpf": c["cpf"], "cargo": cargo})
        print(f"Inscrições criadas: {len(inscritos)}/40")

        # Distribuição:
        # - 10 ficam em Aguardando pagamento (não geraram PIX)
        # - 15 -> PIX gerado + PIX copiado
        # - 15 -> PIX gerado + PIX copiado + PIX baixado
        random.shuffle(inscritos)
        aguardando = inscritos[:10]
        copiados   = inscritos[10:25]
        baixados   = inscritos[25:40]

        # 30 vão pra PIX gerado (todos exceto os "aguardando")
        for ins in copiados + baixados:
            await client.patch(f"{API}/inscricoes/{ins['id']}", json={"status":"PIX gerado"})
        # 30 também vão pra PIX copiado
        for ins in copiados + baixados:
            await client.patch(f"{API}/inscricoes/{ins['id']}", json={"status":"PIX copiado"})
        # 15 vão pra PIX baixado
        for ins in baixados:
            await client.patch(f"{API}/inscricoes/{ins['id']}", json={"status":"PIX baixado"})

        print(f"  - Aguardando pagamento: {len(aguardando)}")
        print(f"  - PIX gerado + copiado: {len(copiados)}")
        print(f"  - PIX gerado + copiado + baixado: {len(baixados)}")

        await enable_tg(client)
        print("Telegram reativado.")

        # Stats final
        s = (await client.get(f"{API}/stats")).json()
        print("\nStats finais:", s)


if __name__ == "__main__":
    asyncio.run(main())
