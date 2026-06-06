"""
Teste de carga: 2.000 inscrições em ~10 minutos (~3.3/s).
Cada inscrição com CPF único, IP brasileiro de regiões variadas.
"""
import os
import sys
import time
import random
import string
import requests
from concurrent.futures import ThreadPoolExecutor

API = os.environ.get("API_URL", "https://noite-chat-1.preview.emergentagent.com") + "/api/donas"

BR_PREFIXES = [
    "200.221","189.10","187.45","201.86","189.7","200.179","200.230","189.6",
    "187.74","201.45","201.78","187.180","189.40","189.79","201.27","189.111",
    "189.39","200.140","200.13","189.115","201.81","201.62","189.91","200.103",
    "201.55","189.50","201.18","189.124","189.46","200.252","189.9","200.142",
    "200.146","200.165","189.18","200.169","200.155",
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
]

TOTAL = 2000
DURATION_S = 600  # 10 minutos
INTERVAL = DURATION_S / TOTAL  # ~0.3s entre rajadas


def random_ip():
    return f"{random.choice(BR_PREFIXES)}.{random.randint(0,255)}.{random.randint(1,254)}"


def cpf_for(i: int) -> str:
    return f"99{str(i).zfill(9)}"  # garante 11 dígitos únicos


def post_inscricao(i: int):
    ip = random_ip()
    nome = random.choice(NOMES_PT) + f" {i}"
    device = "Mobile" if random.random() < 0.7 else "Desktop"
    body = {
        "cpf": cpf_for(i),
        "candidato": nome,
        "dispositivo": device,
        "email": f"teste{i}@example.com",
        "titulo": "ENEM 2026 - Inscrição",
        "payload": {
            "dataNascimento": f"{random.randint(1,28):02d}/{random.randint(1,12):02d}/{random.randint(1990,2008)}",
            "sexo": random.choice(["M", "F"]),
            "linguaEstrangeira": random.choice(["Inglês", "Espanhol"]),
            "ufProvaNome": random.choice(["São Paulo","Bahia","Rio de Janeiro","Pernambuco","Ceará"]),
            "municipioProva": "Capital",
            "nomeDaMae": "Mãe Teste",
        },
    }
    try:
        r = requests.post(
            f"{API}/inscricoes",
            json=body,
            headers={"X-Forwarded-For": ip, "Content-Type": "application/json"},
            timeout=10,
        )
        return r.status_code, r.elapsed.total_seconds()
    except Exception as e:
        return 0, str(e)


def main():
    random.seed(7)
    t0 = time.time()
    ok = 0
    fail = 0
    print(f"=== INICIANDO 2.000 INSCRIÇÕES em ~10 min ===")
    print(f"API: {API}")
    print(f"Intervalo alvo: {INTERVAL*1000:.0f}ms entre cada uma")

    # 8 workers em rajadas pequenas
    with ThreadPoolExecutor(max_workers=8) as pool:
        next_dispatch = t0
        idx = 0
        futures = []
        while idx < TOTAL:
            now = time.time()
            if now >= next_dispatch:
                futures.append(pool.submit(post_inscricao, idx))
                idx += 1
                next_dispatch += INTERVAL
                if idx % 200 == 0:
                    print(f"  [t={now-t0:5.0f}s] disparadas: {idx}/{TOTAL}")
            else:
                time.sleep(0.05)
        # Espera as últimas
        for f in futures:
            code, _ = f.result()
            if code == 200:
                ok += 1
            else:
                fail += 1

    elapsed = time.time() - t0
    print(f"\n=== RESULTADO ===")
    print(f"  duração: {elapsed:.0f}s ({elapsed/60:.1f} min)")
    print(f"  OK   : {ok}/{TOTAL}")
    print(f"  FAIL : {fail}/{TOTAL}")
    print(f"  taxa : {TOTAL/elapsed:.2f} req/s")


if __name__ == "__main__":
    main()
