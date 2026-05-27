"""
Teste de carga: simula 100 visitantes com IPs brasileiros de diversas regiões.

Distribuição:
  - 100 acessam o site (POST /acessos)
  - 50 iniciam inscrição (POST /eventos tipo=inscricao_iniciada)
  - 50 enviam inscrição (POST /inscricoes)
    - 30 dessas 50 geram PIX  (GET /pix/{numero})
      - 15 copiam o PIX        (POST /pix/{numero}/copiado)
      - 15 baixam o PIX        (POST /pix/{numero}/baixado)
        (os 15 que copiaram e os 15 que baixaram são subconjuntos disjuntos dos 30)
"""
import os
import sys
import time
import random
import string
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

API = os.environ.get("API_URL", "https://noite-chat-1.preview.emergentagent.com") + "/api/donas"

# Prefixos /16 conhecidos de provedores brasileiros, por região aproximada.
# A geo lookup (ipwho.is) vai resolver a cidade real de cada IP.
BR_PREFIXES = [
    # Sudeste — São Paulo
    "200.221", "189.10", "187.45", "201.86", "189.7", "200.179",
    # Sudeste — Rio de Janeiro
    "200.230", "189.6", "187.74", "201.45",
    # Sudeste — Minas Gerais
    "201.78", "187.180", "189.40",
    # Sudeste — Espírito Santo
    "189.79",
    # Sul — Paraná
    "200.179", "201.27", "189.111",
    # Sul — Santa Catarina
    "189.39", "200.140",
    # Sul — Rio Grande do Sul
    "200.13", "189.115", "201.81",
    # Nordeste — Bahia
    "201.62", "189.91",
    # Nordeste — Pernambuco
    "200.103", "201.55",
    # Nordeste — Ceará
    "189.50", "201.18",
    # Nordeste — Maranhão
    "189.124",
    # Nordeste — Rio Grande do Norte
    "189.46",
    # Centro-Oeste — Distrito Federal
    "200.252", "189.9",
    # Centro-Oeste — Goiás
    "200.142",
    # Centro-Oeste — Mato Grosso
    "200.146",
    # Norte — Pará
    "200.165", "189.18",
    # Norte — Amazonas
    "200.169",
    # Norte — Tocantins
    "200.155",
]

NOMES_PT = [
    "Ana Paula Silva", "João Pedro Oliveira", "Maria Eduarda Souza", "Carlos Henrique Lima",
    "Beatriz Almeida", "Rafael Costa", "Larissa Ferreira", "Lucas Martins", "Juliana Ribeiro",
    "Gabriel Santos", "Camila Rocha", "Felipe Carvalho", "Mariana Gomes", "Bruno Araújo",
    "Letícia Barbosa", "Vinicius Mendes", "Isabela Pinto", "Thiago Cardoso", "Amanda Pereira",
    "Diego Nascimento", "Sofia Cavalcanti", "Matheus Dias", "Fernanda Teixeira", "Henrique Moreira",
    "Carolina Vieira", "Eduardo Ramos", "Vitória Castro", "Pedro Henrique Cruz", "Yasmin Lopes",
    "Ricardo Monteiro", "Aline Correia", "Daniel Freitas", "Patrícia Andrade", "Gustavo Reis",
    "Natália Campos", "André Borges", "Luana Machado", "Murilo Pires", "Bianca Nogueira",
    "Vinícius Fernandes", "Tatiane Soares", "Leonardo Batista", "Renata Moura", "Igor Cunha",
    "Cláudia Farias", "Marcelo Tavares", "Débora Antunes", "Otávio Sales", "Sabrina Brito",
]


def random_cpf() -> str:
    return ''.join(random.choices(string.digits, k=11))


def random_ip(used: set) -> str:
    for _ in range(50):
        prefix = random.choice(BR_PREFIXES)
        ip = f"{prefix}.{random.randint(0, 255)}.{random.randint(1, 254)}"
        if ip not in used:
            used.add(ip)
            return ip
    # fallback
    ip = f"{random.choice(BR_PREFIXES)}.{random.randint(0,255)}.{random.randint(1,254)}.{random.randint(1,254)}"[:15]
    used.add(ip)
    return ip


def random_date_naturalmente():
    # Idade entre 17 e 35
    year = random.randint(2026 - 35, 2026 - 17)
    month = random.randint(1, 12)
    day = random.randint(1, 28)
    return f"{day:02d}/{month:02d}/{year}"


def hdr(ip: str, device: str) -> dict:
    ua = (
        "Mozilla/5.0 (Linux; Android 13) AppleWebKit/537.36" if device == "Mobile"
        else "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    )
    return {
        "X-Forwarded-For": ip,
        "User-Agent": ua,
        "Content-Type": "application/json",
    }


def post(path: str, body: dict, headers: dict) -> dict:
    r = requests.post(f"{API}{path}", json=body, headers=headers, timeout=15)
    if r.status_code >= 400:
        return {"_err": r.status_code, "_body": r.text[:200]}
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:200]}


def get(path: str, headers: dict) -> dict:
    r = requests.get(f"{API}{path}", headers=headers, timeout=15)
    if r.status_code >= 400:
        return {"_err": r.status_code, "_body": r.text[:200]}
    try:
        return r.json()
    except Exception:
        return {"_raw": r.text[:200]}


def acesso(ip: str, device: str) -> None:
    post("/acessos", {"device": device, "path": "/home.html"}, hdr(ip, device))


def iniciada(ip: str, device: str, cpf: str, nome: str) -> None:
    post("/eventos", {
        "tipo": "inscricao_iniciada",
        "cpf": cpf,
        "candidato": nome,
        "dispositivo": device,
    }, hdr(ip, device))


def enviada(ip: str, device: str, cpf: str, nome: str) -> str:
    # Payload simples que reflete o que o frontend salva
    payload = {
        "candidato": nome,
        "cpf": cpf,
        "dataNascimento": random_date_naturalmente(),
        "linguaEstrangeira": random.choice(["Inglês", "Espanhol"]),
        "ufProvaNome": random.choice(["São Paulo", "Bahia", "Rio de Janeiro", "Pernambuco", "Ceará", "Minas Gerais", "Paraná"]),
        "municipioProva": random.choice(["Capital", "Interior"]),
        "sexo": random.choice(["M", "F"]),
        "nomeDaMae": "Mãe de " + nome.split()[0],
    }
    body = {
        "cpf": cpf,
        "candidato": nome,
        "dispositivo": device,
        "titulo": "ENEM 2026 - Inscrição",
        "payload": payload,
    }
    out = post("/inscricoes", body, hdr(ip, device))
    return out.get("numero", "")


def gerar_pix(ip: str, device: str, numero: str) -> None:
    get(f"/pix/{numero}", hdr(ip, device))


def copiar_pix(ip: str, device: str, numero: str) -> None:
    post(f"/pix/{numero}/copiado", {}, hdr(ip, device))


def baixar_pix(ip: str, device: str, numero: str) -> None:
    post(f"/pix/{numero}/baixado", {}, hdr(ip, device))


def run_visitor(idx: int, ip: str, fluxo_completo: bool) -> dict:
    device = "Mobile" if random.random() < 0.65 else "Desktop"
    nome = random.choice(NOMES_PT) + " " + random.choice(["Filho", "Júnior", ""]).strip()
    nome = nome.strip()
    cpf = random_cpf()
    result = {"idx": idx, "ip": ip, "device": device, "nome": nome, "cpf": cpf, "numero": ""}

    try:
        acesso(ip, device)
        if not fluxo_completo:
            return result
        # pequeno delay realista
        time.sleep(0.05)
        iniciada(ip, device, cpf, nome)
        time.sleep(0.05)
        numero = enviada(ip, device, cpf, nome)
        result["numero"] = numero
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


def main():
    random.seed(42)
    used_ips: set = set()
    ips = [random_ip(used_ips) for _ in range(100)]
    # 50 só acessam, 50 fluxo completo
    flags = [False] * 50 + [True] * 50
    random.shuffle(flags)

    print(f"=== INICIANDO 100 TESTES (50 só acesso + 50 fluxo completo) ===")
    print(f"API: {API}")

    results = []
    # Executa em paralelo limitado (8 workers) para evitar rate limit do ipwho.is
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(run_visitor, i, ips[i], flags[i]): i for i in range(100)
        }
        for fut in as_completed(futures):
            results.append(fut.result())

    results.sort(key=lambda x: x["idx"])
    print(f"\n=== ETAPA 1 COMPLETA: 100 acessos + 50 inscrições iniciadas/enviadas ===")

    # Identifica as inscrições enviadas (com número)
    inscricoes_enviadas = [r for r in results if r.get("numero")]
    print(f"Inscrições enviadas com sucesso: {len(inscricoes_enviadas)}")

    if len(inscricoes_enviadas) < 30:
        print("ERRO: menos de 30 inscrições enviadas — não há como gerar 30 PIX. Abortando etapa 2.")
        return

    # 30 das 50 vão gerar PIX
    geram_pix = inscricoes_enviadas[:30]
    print(f"\n=== ETAPA 2: gerando PIX para 30 inscrições ===")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda r: gerar_pix(r["ip"], r["device"], r["numero"]), geram_pix))

    # Dos 30 que geraram, 15 copiam (índices 0-14) e 15 baixam (índices 15-29)
    copiam = geram_pix[:15]
    baixam = geram_pix[15:30]

    print(f"\n=== ETAPA 3: 15 PIX copiados ===")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda r: copiar_pix(r["ip"], r["device"], r["numero"]), copiam))

    print(f"\n=== ETAPA 4: 15 PIX baixados ===")
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda r: baixar_pix(r["ip"], r["device"], r["numero"]), baixam))

    print(f"\n=== TUDO PRONTO ===")
    print(f"  • {len(results)} acessos")
    print(f"  • {len(inscricoes_enviadas)} inscrições iniciadas + enviadas")
    print(f"  • {len(geram_pix)} PIX gerados")
    print(f"  • {len(copiam)} PIX copiados")
    print(f"  • {len(baixam)} PIX baixados")


if __name__ == "__main__":
    main()
