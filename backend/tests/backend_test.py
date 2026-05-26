"""
Backend regression tests for ENEM/Donas FastAPI app.
Covers: health, stats, inscricoes, acessos tracker, full create→get persistence.
"""
import os
import time
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://heart-connection-28.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


# ---------- Health ----------
class TestHealth:
    def test_api_root(self, session):
        r = session.get(f"{API}/")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "ok"
        assert "message" in data


# ---------- Stats ----------
class TestStats:
    def test_stats_shape(self, session):
        r = session.get(f"{API}/donas/stats")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("acessos", "inscricoes", "valorTotal", "pixGerados", "pixBaixados"):
            assert k in d, f"Missing key {k} in stats response"
        assert isinstance(d["acessos"], int)
        assert isinstance(d["inscricoes"], int)
        assert isinstance(d["valorTotal"], (int, float))
        assert isinstance(d["pixGerados"], int)
        assert isinstance(d["pixBaixados"], int)


# ---------- Acessos tracker ----------
class TestAcessos:
    def test_log_acesso(self, session):
        before = session.get(f"{API}/donas/stats").json()["acessos"]
        payload = {"path": "/__test__/regression", "ua": "pytest-agent", "device": "Desktop"}
        r = session.post(f"{API}/donas/acessos", json=payload)
        assert r.status_code == 200, r.text
        doc = r.json()
        assert doc.get("path") == "/__test__/regression"
        assert doc.get("ts")
        assert "_id" not in doc  # mongo _id must be stripped
        # verify it appears in list
        time.sleep(0.4)
        listing = session.get(f"{API}/donas/acessos").json()
        assert any(a.get("path") == "/__test__/regression" for a in listing[:50])
        after = session.get(f"{API}/donas/stats").json()["acessos"]
        assert after >= before + 1


# ---------- Inscrições list ----------
class TestInscricoesList:
    def test_list_returns_json(self, session):
        r = session.get(f"{API}/donas/inscricoes")
        assert r.status_code == 200, r.text
        data = r.json()
        assert isinstance(data, list)
        for row in data[:5]:
            assert "_id" not in row, "MongoDB _id should not leak"


# ---------- Full flow Cadastro -> Inscricao -> PIX ----------
TEST_CPF = "00000000191"  # valid format, 11 digits

@pytest.fixture(scope="module")
def created_inscricao(session):
    # 1) cadastro upsert
    cad = {
        "cpf": TEST_CPF,
        "nome": "TEST_REGRESSION USER",
        "email": "TEST_regress@example.com",
        "senha": "Senha123!",
    }
    r = session.post(f"{API}/donas/cadastros", json=cad)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("nome") == "TEST_REGRESSION USER"
    assert "_id" not in body

    # 2) create inscricao
    insc_payload = {
        "cpf": TEST_CPF,
        "candidato": "TEST_REGRESSION USER",
        "email": "TEST_regress@example.com",
        "dispositivo": "Desktop",
        "payload": {
            "linguaEstrangeira": "Inglês",
            "ufProvaNome": "São Paulo",
            "municipioProva": "São Paulo",
        },
    }
    r = session.post(f"{API}/donas/inscricoes", json=insc_payload)
    assert r.status_code == 200, r.text
    insc = r.json()
    assert insc.get("cpf") == TEST_CPF
    assert insc.get("numero")
    assert "_id" not in insc
    yield insc

    # cleanup
    if insc.get("id"):
        session.delete(f"{API}/donas/inscricoes/{insc['id']}")
    session.delete(f"{API}/donas/cadastros/{TEST_CPF}")


class TestInscricaoFlow:
    def test_inscricao_persisted(self, session, created_inscricao):
        # Verify inscricao appears in list endpoint
        listing = session.get(f"{API}/donas/inscricoes").json()
        cpfs = [r.get("cpf") for r in listing]
        assert TEST_CPF in cpfs

    def test_inscricao_idempotent_same_cpf(self, session, created_inscricao):
        # creating again with same CPF should return same numero (no duplicate)
        r = session.post(f"{API}/donas/inscricoes", json={
            "cpf": TEST_CPF,
            "candidato": "TEST_REGRESSION USER UPDATED",
            "payload": {"linguaEstrangeira": "Espanhol"},
        })
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("numero") == created_inscricao.get("numero")

    def test_pix_requires_config(self, session, created_inscricao):
        """PIX endpoint: either returns brcode or 400 if chave not configured."""
        insc_id = created_inscricao.get("id")
        r = session.get(f"{API}/donas/pix/{insc_id}")
        assert r.status_code in (200, 400), f"Unexpected: {r.status_code} {r.text}"
        if r.status_code == 200:
            d = r.json()
            assert d.get("numero")
            assert d.get("brcode")
            assert d.get("valor") == 85.0
            assert d.get("valorFmt") == "R$ 85,00"
        else:
            # configuration missing — expected on fresh env
            assert "PIX" in r.text or "Chave" in r.text


# ---------- Config ----------
class TestConfig:
    def test_get_config(self, session):
        r = session.get(f"{API}/donas/config")
        assert r.status_code == 200, r.text
        d = r.json()
        assert "tgEnabled" in d


# ---------- Static pages (SPA fallback) ----------
class TestStaticPages:
    @pytest.mark.parametrize("path", [
        "/home.html", "/dados.html", "/pais.html", "/nome-social.html",
        "/ensino-medio.html", "/tipo-escola.html", "/municipio-nascimento.html",
        "/atendimento.html", "/lingua.html", "/cep.html", "/endereco.html",
        "/municipio-prova.html", "/contato.html", "/confirma.html",
        "/inscricao-sucesso.html", "/inscricao-concluida.html",
        "/pagamento.html", "/donaspainel.html",
    ])
    def test_page_loads(self, session, path):
        r = session.get(f"{BASE_URL}{path}")
        assert r.status_code == 200, f"{path} -> {r.status_code}"
        assert "<!doctype html>" in r.text.lower() or "<html" in r.text.lower()

    def test_questionario_pages_removed(self, session):
        """questionario.html should not return a real questionnaire — file was removed.
        With SPA fallback this returns 200 with React shell; verify the actual
        questionario file is not present (no .css-... questionnaire markers)."""
        r = session.get(f"{BASE_URL}/questionario.html")
        # We accept 200 (SPA fallback) or 404, but body must NOT contain old questionnaire content
        body_lower = r.text.lower()
        # generic SPA shell markers OK; old questionnaire used "perfil" form fields
        assert "questionario" not in body_lower or "static/js/bundle.js" in body_lower, \
            "Old questionario page seems to still be served"
