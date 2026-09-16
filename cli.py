import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
import unicodedata


def request(server, path, method="GET", data=None, headers=None, multipart=None):
    url = server.rstrip("/") + path
    body = None
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if multipart is not None:
        boundary = "----KnowledgeVault" + uuid.uuid4().hex
        chunks = []
        for name, value in multipart.get("fields", {}).items():
            chunks.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode())
            chunks.append(str(value).encode("utf-8"))
            chunks.append(b"\r\n")
        for file_info in multipart.get("files", []):
            filename = os.path.basename(file_info["filename"])
            content = file_info["content"]
            chunks.append(
                f"--{boundary}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"{filename}\"\r\n"
                f"Content-Type: {file_info.get('content_type', 'application/octet-stream')}\r\n\r\n".encode("utf-8")
            )
            chunks.append(content)
            chunks.append(b"\r\n")
        chunks.append(f"--{boundary}--\r\n".encode())
        body = b"".join(chunks)
        hdrs["Content-Type"] = f"multipart/form-data; boundary={boundary}"
    elif data is not None:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=body, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8")
            return r.status, json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw}
        return e.code, payload
    except Exception as e:
        print(f"서버 접속 실패: {e}")
        return 0, {"detail": str(e)}


def print_items(items):
    if not items:
        print("검색 결과가 없습니다.")
        return
    for item in items:
        files = item.get("attachments") or []
        print(f"[{item['id']}] {item['title']}  <{item.get('category') or '미분류'}>")
        preview = " ".join((item.get("content") or "").split())
        if preview:
            print(f"    {preview[:140]}")
        if files:
            print(f"    첨부: {', '.join(x['filename'] for x in files)}")
        print(f"    수정: {item.get('updated_at','')}")


def search_items(server, query):
    q = urllib.parse.quote(query)
    code, data = request(server, f"/api/search?q={q}&limit=30")
    return data.get("items", []) if code == 200 else []


def autocomplete_search(server, prefix):
    items = search_items(server, prefix) if prefix else []
    return [x["title"] for x in items if x.get("title")]


def category_items(server, category):
    q = urllib.parse.quote(category)
    code, data = request(server, f"/api/knowledge?category={q}&limit=5000")
    return data.get("items", []) if code == 200 else []


def list_categories(server):
    code, data = request(server, "/api/categories")
    if code != 200:
        print(data.get("detail", data))
        return []
    categories = data.get("categories", [])
    print("카테고리")
    print("-" * 40)
    print("[전체]")
    for name in categories:
        print(f"[{name}]")
    print(f"\n총 {len(categories)}개")
    return categories


def autocomplete_categories(server, prefix):
    code, data = request(server, "/api/categories")
    if code != 200:
        return []
    prefix = prefix.lower()
    return [x for x in data.get("categories", []) if x.lower().startswith(prefix)]


def redraw_input(prompt, old, new):
    # 한글은 콘솔에서 2칸으로 표시될 수 있으므로 단순 backspace 대신
    # 줄 전체를 다시 그려 커서가 밀리는 현상을 방지합니다.
    old_width = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in old)
    new_width = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in new)
    sys.stdout.write("\r" + prompt + new + " " * max(0, old_width - new_width))
    sys.stdout.write("\r" + prompt + new)
    sys.stdout.flush()


def console_input(prompt="", completions=None):
    """Windows cmd에서 Tab 자동완성, Backspace, 화살표 히스토리를 지원합니다."""
    if os.name != "nt":
        return input(prompt)
    import msvcrt

    sys.stdout.write(prompt)
    sys.stdout.flush()
    buf = ""
    history = getattr(console_input, "history", [])
    history_pos = len(history)
    completion_index = 0
    completion_prefix = None
    completion_suggestions = []
    completion_shown = False
    completion_active = False

    while True:
        ch = msvcrt.getwch()
        if ch in ("\r", "\n"):
            print()
            if buf.strip():
                history.append(buf)
                console_input.history = history[-50:]
            return buf
        if ch == "\x03":
            print("^C")
            raise KeyboardInterrupt
        if ch == "\x08":
            if buf:
                old = buf
                buf = buf[:-1]
                redraw_input(prompt, old, buf)
            completion_prefix = None
            completion_suggestions = []
            completion_index = 0
            completion_shown = False
            completion_active = False
            continue
        if ch == "\t":
            lower = buf.lower()
            if (lower.startswith("search ") or lower.startswith("s ")) and completions is not None:
                # 첫 Tab에서 입력한 원래 prefix를 보존합니다.
                # 첫 후보로 buf가 바뀌더라도 다음 Tab에서 buf를 다시 prefix로
                # 해석하지 않고, 같은 후보 목록을 계속 순환합니다.
                if not completion_active:
                    completion_prefix = buf.split(None, 1)[1].strip() if len(buf.split(None, 1)) > 1 else ""
                    completion_suggestions = (
                        completions(completion_prefix) if completion_prefix else []
                    )
                    completion_index = 0
                    completion_shown = False
                    completion_active = bool(completion_suggestions)

                if completion_suggestions:
                    if not completion_shown:
                        print()
                        print("자동완성 후보:")
                        for i, title in enumerate(completion_suggestions[:10], 1):
                            print(f"  {i}. {title}")
                        if len(completion_suggestions) > 10:
                            print(f"  ... 외 {len(completion_suggestions) - 10}개")
                        completion_shown = True
                    suggestion = completion_suggestions[completion_index % len(completion_suggestions)]
                    completion_index += 1
                    old = buf
                    buf = ("s " if lower.startswith("s ") else "search ") + suggestion
                    redraw_input(prompt, old, buf)
            elif lower.startswith("category ") or lower.startswith("c "):
                if not completion_active:
                    completion_prefix = buf.split(None, 1)[1].strip() if len(buf.split(None, 1)) > 1 else ""
                    completion_suggestions = (
                        autocomplete_categories(SERVER_FOR_COMPLETION, completion_prefix)
                        if completion_prefix else []
                    )
                    completion_index = 0
                    completion_shown = False
                    completion_active = bool(completion_suggestions)

                if completion_suggestions:
                    if not completion_shown:
                        print()
                        print("카테고리 후보:")
                        for i, name in enumerate(completion_suggestions[:10], 1):
                            print(f"  {i}. {name}")
                        if len(completion_suggestions) > 10:
                            print(f"  ... 외 {len(completion_suggestions) - 10}개")
                        completion_shown = True
                    suggestion = completion_suggestions[completion_index % len(completion_suggestions)]
                    completion_index += 1
                    old = buf
                    buf = ("c " if lower.startswith("c ") else "category ") + suggestion
                    redraw_input(prompt, old, buf)
            continue
        if ch in ("\x00", "\xe0"):
            key = msvcrt.getwch()
            if key == "H" and history:
                if history_pos > 0:
                    history_pos -= 1
                    old = buf
                    buf = history[history_pos]
                    redraw_input(prompt, old, buf)
                    completion_active = False
                    completion_suggestions = []
                    completion_index = 0
                    completion_shown = False
            elif key == "P" and history:
                if history_pos < len(history) - 1:
                    history_pos += 1
                    old = buf
                    buf = history[history_pos]
                else:
                    old = buf
                    history_pos = len(history)
                    buf = ""
                redraw_input(prompt, old, buf)
                completion_active = False
                completion_suggestions = []
                completion_index = 0
                completion_shown = False
            continue
        if ord(ch) >= 32:
            buf += ch
            sys.stdout.write(ch)
            sys.stdout.flush()
            history_pos = len(history)
            completion_prefix = None
            completion_suggestions = []
            completion_index = 0
            completion_shown = False
            completion_active = False


def read_multiline():
    print("내용 입력. 빈 줄을 두 번 연속 입력하면 저장합니다.")
    lines = []
    empty_count = 0
    while True:
        line = input()
        if line == "":
            empty_count += 1
            if empty_count >= 2:
                break
            lines.append("")
        else:
            empty_count = 0
            lines.append(line)
    # 종료용 빈 줄은 제거하되, 첫 번째 빈 줄은 내용의 마지막 줄바꿈으로 유지
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def prompt_files():
    raw = input("첨부파일 경로 (없으면 Enter, 여러 개는 ; 로 구분): ").strip()
    if not raw:
        return []
    files = []
    for raw_path in raw.split(";"):
        path = raw_path.strip().strip('"')
        if not path:
            continue
        if not os.path.isfile(path):
            print(f"파일을 찾을 수 없습니다: {path}")
            continue
        with open(path, "rb") as f:
            content = f.read()
        files.append({"filename": os.path.basename(path), "content": content})
    return files


def interactive(server):
    global SERVER_FOR_COMPLETION
    SERVER_FOR_COMPLETION = server
    print(f"Knowledge Vault CLI  |  {server}")
    print("명령: s/search <단어>, c/category <이름>, cl/categories, v/view <id>, n/add, e/edit <id>, d/delete <id>, h/help, q/quit")
    while True:
        try:
            line = console_input("vault> ", lambda prefix: autocomplete_search(server, prefix))
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not line.strip():
            continue
        parts = line.strip().split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1] if len(parts) > 1 else ""
        if cmd in {"quit", "exit", "q"}:
            return
        if cmd in {"help", "h"}:
            print("s/search <검색어> | c/category <카테고리> | cl/categories | v/view <ID> | n/add | e/edit <ID> | d/delete <ID> | h/help | q/quit")
            print("search 뒤에서 Tab을 누르면 지식 제목으로 자동완성됩니다.")
            print("category 뒤에서 Tab을 누르면 카테고리명으로 자동완성됩니다.")
            print("categories: 카테고리 종류 조회")
            print("category <이름>: 해당 카테고리의 전체 지식 조회")
        elif cmd in {"search", "s"}:
            if not arg:
                print("검색어를 입력하세요.")
                continue
            items = search_items(server, arg)
            if items:
                print_items(items)
            else:
                print("검색 결과가 없습니다.")
        elif cmd in {"categories", "cats", "cl"}:
            list_categories(server)
        elif cmd in {"category", "cat", "c"}:
            if not arg:
                print("카테고리명을 입력하세요. categories로 종류를 확인할 수 있습니다.")
                continue
            items = category_items(server, arg)
            print(f"\n[{arg}] 카테고리 지식 {len(items)}개")
            print_items(items)
        elif cmd in {"view", "v"}:
            show_view(server, arg)
        elif cmd in {"add", "n"}:
            add_knowledge(server)
        elif cmd in {"edit", "e"}:
            edit_knowledge(server, arg)
        elif cmd in {"delete", "d"}:
            delete_knowledge(server, arg)
        else:
            print("알 수 없는 명령입니다. help를 입력하세요.")


def show_view(server, arg):
    try:
        kid = int(arg)
    except ValueError:
        print("ID는 숫자입니다.")
        return
    code, item = request(server, f"/api/knowledge/{kid}")
    if code != 200:
        print(item.get("detail", item))
        return
    print("\n" + "=" * 60)
    print(f"[{item['id']}] {item['title']}")
    print(f"카테고리: {item.get('category') or '미분류'}")
    print(f"태그: {item.get('tags','')}")
    print("-" * 60)
    print(item.get("content", ""))
    files = item.get("attachments") or []
    if files:
        print("\n첨부파일:")
        for f in files:
            print(f"  - {f['filename']}  {f['url']}")
    print("=" * 60 + "\n")


def add_knowledge(server):
    title = input("제목: ").strip()
    if not title:
        return
    category = input("카테고리 [미분류]: ").strip()
    tags = input("태그: ").strip()
    content = read_multiline()
    files = prompt_files()
    multipart = {
        "fields": {"title": title, "category": category, "tags": tags, "content": content},
        "files": files,
    }
    code, data = request(server, "/api/knowledge", "POST", multipart=multipart)
    print(f"저장 완료: ID {data.get('id')}" if code == 200 else data.get("detail", data))


def edit_knowledge(server, arg):
    try:
        kid = int(arg)
    except ValueError:
        print("ID는 숫자입니다.")
        return
    code, item = request(server, f"/api/knowledge/{kid}")
    if code != 200:
        print(item.get("detail", item))
        return
    print(f"현재 제목: {item['title']}")
    title = input("새 제목 (Enter=유지): ").strip() or item["title"]
    category = input(f"카테고리 [{item['category']}]: ").strip() or item["category"]
    tags = input(f"태그 [{item.get('tags','')}]: ").strip()
    if tags == "":
        tags = item.get("tags", "")
    print("내용을 새로 입력하려면 첫 줄부터 입력하세요. Enter만 누르면 기존 내용 유지.")
    first = input()
    if first == "":
        content = item.get("content", "")
    else:
        print("이어서 입력합니다. 빈 줄을 두 번 연속 입력하면 저장합니다.")
        lines = [first]
        empty_count = 0
        while True:
            line = input()
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
                lines.append("")
            else:
                empty_count = 0
                lines.append(line)
        while lines and lines[-1] == "":
            lines.pop()
        content = "\n".join(lines)
    files = prompt_files()
    multipart = {
        "fields": {"title": title, "category": category, "tags": tags, "content": content},
        "files": files,
    }
    code, data = request(server, f"/api/knowledge/{kid}", "PUT", multipart=multipart)
    print("수정 완료" if code == 200 else data.get("detail", data))


def delete_knowledge(server, arg):
    try:
        kid = int(arg)
    except ValueError:
        print("ID는 숫자입니다.")
        return
    if input(f"{kid}번 지식을 삭제할까요? [y/N]: ").lower() != "y":
        return
    code, data = request(server, f"/api/knowledge/{kid}", "DELETE")
    print("삭제 완료" if code == 200 else data.get("detail", data))


SERVER_FOR_COMPLETION = "http://127.0.0.1:8000"

def main():
    parser = argparse.ArgumentParser(description="Knowledge Vault CLI")
    parser.add_argument("--server", default=os.getenv("KNOWLEDGE_VAULT_SERVER", "http://127.0.0.1:8000"))
    parser.add_argument("command", nargs="*")
    args = parser.parse_args()
    if not args.command:
        interactive(args.server)
        return
    cmd = args.command[0]
    arg = " ".join(args.command[1:])
    if cmd in {"search", "s"}:
        code, data = request(args.server, "/api/search?q=" + urllib.parse.quote(arg) + "&limit=30")
        print_items(data.get("items", [])) if code == 200 else print(data.get("detail", data))
    elif cmd in {"categories", "cats", "cl"}:
        list_categories(args.server)
    elif cmd in {"category", "cat", "c"}:
        if not arg:
            print("카테고리명을 입력하세요.")
        else:
            items = category_items(args.server, arg)
            print(f"\n[{arg}] 카테고리 지식 {len(items)}개")
            print_items(items)
    elif cmd in {"view", "v"}:
        show_view(args.server, arg)
    elif cmd in {"add", "n"}:
        add_knowledge(args.server)
    elif cmd in {"edit", "e"}:
        edit_knowledge(args.server, arg)
    elif cmd in {"delete", "d"}:
        delete_knowledge(args.server, arg)
    else:
        interactive(args.server)


if __name__ == "__main__":
    main()
