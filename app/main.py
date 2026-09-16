from pathlib import Path
from datetime import datetime
import sqlite3
import shutil
import zipfile

from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "knowledge.db"
BACKUP_DIR = DATA_DIR / "backup"
ATTACHMENTS_DIR = DATA_DIR / "attachments"

DATA_DIR.mkdir(exist_ok=True)
BACKUP_DIR.mkdir(exist_ok=True)
ATTACHMENTS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Knowledge Vault")
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
app.mount("/attachments", StaticFiles(directory=ATTACHMENTS_DIR), name="attachments")
templates = Jinja2Templates(directory=BASE_DIR / "templates")



def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db():
    conn = get_conn()
    try:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS knowledge (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            content TEXT NOT NULL DEFAULT '',
            category TEXT NOT NULL DEFAULT '기타',
            tags TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            knowledge_id INTEGER NOT NULL,
            filename TEXT NOT NULL,
            content_type TEXT NOT NULL DEFAULT 'application/octet-stream',
            file_size INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            UNIQUE(knowledge_id, filename),
            FOREIGN KEY(knowledge_id) REFERENCES knowledge(id) ON DELETE CASCADE
        );

        CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(
            title, content, tags,
            content='knowledge',
            content_rowid='id',
            tokenize='unicode61'
        );

        CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
            INSERT INTO knowledge_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS knowledge_ad AFTER DELETE ON knowledge BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
        END;
        CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
            INSERT INTO knowledge_fts(knowledge_fts, rowid, title, content, tags)
            VALUES ('delete', old.id, old.title, old.content, old.tags);
            INSERT INTO knowledge_fts(rowid, title, content, tags)
            VALUES (new.id, new.title, new.content, new.tags);
        END;
        """)
        conn.commit()
    finally:
        conn.close()


@app.on_event("startup")
def startup():
    init_db()


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"categories": get_categories()},
    )


def get_categories():
    conn = get_conn()
    try:
        return [r["name"] for r in conn.execute(
            "SELECT name FROM categories ORDER BY name COLLATE NOCASE"
        ).fetchall()]
    finally:
        conn.close()


def attachment_dict(row):
    item = dict(row)
    item["url"] = f"/attachments/{item['knowledge_id']}/{item['filename']}"
    return item


def get_attachments(knowledge_id: int):
    conn = get_conn()
    try:
        rows = conn.execute(
            "SELECT id, knowledge_id, filename, content_type, file_size, created_at "
            "FROM attachments WHERE knowledge_id=? ORDER BY id",
            (knowledge_id,),
        ).fetchall()
        return [attachment_dict(r) for r in rows]
    finally:
        conn.close()


def attachment_path(knowledge_id: int, filename: str) -> Path:
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise HTTPException(400, "올바른 파일명이 아닙니다.")
    directory = ATTACHMENTS_DIR / str(knowledge_id)
    directory.mkdir(parents=True, exist_ok=True)
    return directory / safe_name


@app.get("/api/categories")
def categories():
    return {"categories": get_categories()}


@app.post("/api/categories")
def add_category(payload: dict):
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(400, "카테고리명을 입력하세요.")
    conn = get_conn()
    try:
        existing = conn.execute("SELECT 1 FROM categories WHERE name=?", (name,)).fetchone()
        if existing:
            raise HTTPException(409, "이미 존재하는 카테고리입니다.")
        conn.execute(
            "INSERT INTO categories(name, created_at) VALUES (?, ?)",
            (name, datetime.now().isoformat(timespec="seconds")),
        )
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "categories": get_categories()}


@app.delete("/api/categories")
def delete_category(name: str):
    name = name.strip()
    if not name:
        raise HTTPException(400, "카테고리명이 필요합니다.")
    conn = get_conn()
    try:
        existing = conn.execute("SELECT 1 FROM categories WHERE name=?", (name,)).fetchone()
        if not existing:
            raise HTTPException(404, "카테고리를 찾을 수 없습니다.")
        # 카테고리를 삭제해도 지식은 삭제하지 않고 미분류로 남깁니다.
        conn.execute("UPDATE knowledge SET category='' WHERE category=?", (name,))
        conn.execute("DELETE FROM categories WHERE name=?", (name,))
        conn.commit()
    finally:
        conn.close()
    return {"ok": True, "categories": get_categories()}


@app.get("/api/knowledge")
def list_knowledge(category: str = "", limit: int = 100):
    limit = min(max(limit, 1), 5000)
    conn = get_conn()
    try:
        if category:
            rows = conn.execute(
                """SELECT id, title, content, category, tags, created_at, updated_at
                   FROM knowledge WHERE category=?
                   ORDER BY updated_at DESC LIMIT ?""",
                (category, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT id, title, content, category, tags, created_at, updated_at
                   FROM knowledge ORDER BY updated_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        items = [dict(r) for r in rows]
        for item in items:
            item["attachments"] = get_attachments(item["id"])
        return {"items": items}
    finally:
        conn.close()


@app.get("/api/knowledge/{knowledge_id}")
def get_knowledge(knowledge_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()
        if not row:
            raise HTTPException(404, "지식을 찾을 수 없습니다.")
        item = dict(row)
        item["attachments"] = get_attachments(knowledge_id)
        return item
    finally:
        conn.close()


@app.get("/api/search")
def search(q: str = "", category: str = "", limit: int = 30):
    q = q.strip()
    limit = min(max(limit, 1), 100)
    conn = get_conn()
    try:
        if not q:
            sql = """SELECT id, title, content, category, tags, updated_at
                     FROM knowledge {where}
                     ORDER BY updated_at DESC LIMIT ?"""
            if category:
                rows = conn.execute(sql.format(where="WHERE category=?"), (category, limit)).fetchall()
            else:
                rows = conn.execute(sql.format(where=""), (limit,)).fetchall()
        else:
            terms = [x for x in q.replace('"', " ").split() if x]
            match_q = " ".join(f'"{x}"*' for x in terms) or '""'
            if category:
                rows = conn.execute(
                    """SELECT k.id, k.title, k.content, k.category, k.tags, k.updated_at
                       FROM knowledge_fts f JOIN knowledge k ON k.id=f.rowid
                       WHERE knowledge_fts MATCH ? AND k.category=?
                       ORDER BY bm25(knowledge_fts), k.updated_at DESC LIMIT ?""",
                    (match_q, category, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """SELECT k.id, k.title, k.content, k.category, k.tags, k.updated_at
                       FROM knowledge_fts f JOIN knowledge k ON k.id=f.rowid
                       WHERE knowledge_fts MATCH ?
                       ORDER BY bm25(knowledge_fts), k.updated_at DESC LIMIT ?""",
                    (match_q, limit),
                ).fetchall()
        items = [dict(r) for r in rows]
        for item in items:
            item["attachments"] = get_attachments(item["id"])
        return {"items": items}
    finally:
        conn.close()


@app.post("/api/knowledge")
async def create_knowledge(
    title: str = Form(...),
    content: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    title = title.strip()
    if not title:
        raise HTTPException(400, "제목을 입력하세요.")
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    try:
        cur = conn.execute(
            """INSERT INTO knowledge(title, content, category, tags, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (title, content, category.strip(), tags.strip(), now, now),
        )
        knowledge_id = cur.lastrowid
        conn.commit()
    finally:
        conn.close()

    if files:
        await save_attachments(knowledge_id, files)
    return {"id": knowledge_id, "attachments": get_attachments(knowledge_id)}


@app.put("/api/knowledge/{knowledge_id}")
async def update_knowledge(
    knowledge_id: int,
    title: str = Form(...),
    content: str = Form(""),
    category: str = Form(""),
    tags: str = Form(""),
    files: list[UploadFile] = File(default=[]),
):
    title = title.strip()
    if not title:
        raise HTTPException(400, "제목을 입력하세요.")
    now = datetime.now().isoformat(timespec="seconds")
    conn = get_conn()
    try:
        cur = conn.execute(
            """UPDATE knowledge
               SET title=?, content=?, category=?, tags=?, updated_at=?
               WHERE id=?""",
            (title, content, category.strip(), tags.strip(), now, knowledge_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "지식을 찾을 수 없습니다.")
        conn.commit()
    finally:
        conn.close()
    if files:
        await save_attachments(knowledge_id, files)
    return {"ok": True, "attachments": get_attachments(knowledge_id)}


async def save_attachments(knowledge_id: int, files: list[UploadFile]):
    directory = ATTACHMENTS_DIR / str(knowledge_id)
    directory.mkdir(parents=True, exist_ok=True)
    conn = get_conn()
    try:
        for upload in files:
            if not upload.filename:
                continue
            path = attachment_path(knowledge_id, upload.filename)
            with path.open("wb") as output:
                shutil.copyfileobj(upload.file, output)
            size = path.stat().st_size
            conn.execute(
                """INSERT INTO attachments(knowledge_id, filename, content_type, file_size, created_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(knowledge_id, filename) DO UPDATE SET
                     content_type=excluded.content_type,
                     file_size=excluded.file_size""",
                (
                    knowledge_id,
                    path.name,
                    upload.content_type or "application/octet-stream",
                    size,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )
        conn.commit()
    finally:
        conn.close()
        for upload in files:
            await upload.close()


@app.post("/api/knowledge/{knowledge_id}/attachments")
async def upload_attachments(knowledge_id: int, files: list[UploadFile] = File(default=[])):
    conn = get_conn()
    try:
        exists = conn.execute("SELECT 1 FROM knowledge WHERE id=?", (knowledge_id,)).fetchone()
    finally:
        conn.close()
    if not exists:
        raise HTTPException(404, "지식을 찾을 수 없습니다.")
    await save_attachments(knowledge_id, files)
    return {"ok": True, "attachments": get_attachments(knowledge_id)}


@app.delete("/api/attachments/{attachment_id}")
def delete_attachment(attachment_id: int):
    conn = get_conn()
    try:
        row = conn.execute("SELECT * FROM attachments WHERE id=?", (attachment_id,)).fetchone()
        if not row:
            raise HTTPException(404, "첨부파일을 찾을 수 없습니다.")
        path = attachment_path(row["knowledge_id"], row["filename"])
        conn.execute("DELETE FROM attachments WHERE id=?", (attachment_id,))
        conn.commit()
    finally:
        conn.close()
    if path.exists():
        path.unlink()
    return {"ok": True}


@app.delete("/api/knowledge/{knowledge_id}")
def delete_knowledge(knowledge_id: int):
    conn = get_conn()
    try:
        cur = conn.execute("DELETE FROM knowledge WHERE id=?", (knowledge_id,))
        if cur.rowcount == 0:
            raise HTTPException(404, "지식을 찾을 수 없습니다.")
        conn.commit()
    finally:
        conn.close()
    shutil.rmtree(ATTACHMENTS_DIR / str(knowledge_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/backup")
def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destination = BACKUP_DIR / f"knowledge_{timestamp}.zip"
    temp_db = BACKUP_DIR / f".knowledge_{timestamp}.db"
    source = get_conn()
    try:
        target = sqlite3.connect(temp_db)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()
    try:
        with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(temp_db, "knowledge.db")
            if ATTACHMENTS_DIR.exists():
                for path in ATTACHMENTS_DIR.rglob("*"):
                    if path.is_file():
                        zf.write(path, path.relative_to(DATA_DIR).as_posix())
    finally:
        temp_db.unlink(missing_ok=True)
    return {"ok": True, "file": destination.name}


@app.get("/health")
def health():
    return {"status": "ok"}
