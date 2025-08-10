from flask import Flask, render_template, request, redirect, url_for, session, flash
import json, os, datetime
from item import Item
from UserSystem import UserSystem
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "도전자비밀키123!")

# 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ITEMS_FILE = os.path.join(BASE_DIR, "items.json")
LOG_FILE = os.path.join(BASE_DIR, "rent_log.json")
USERS_FILE = os.path.join(BASE_DIR, "users.json")
MESSAGES_FILE = os.path.join(BASE_DIR, "messages.json")

user_system = UserSystem(USERS_FILE)

# ---------- 유틸 ----------
def load_items():
    if not os.path.exists(ITEMS_FILE):
        save_items([])
        return []
    with open(ITEMS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_items(items):
    with open(ITEMS_FILE, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

def load_messages():
    if not os.path.exists(MESSAGES_FILE):
        save_messages([])
        return []
    with open(MESSAGES_FILE, "r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return []

def save_messages(messages):
    with open(MESSAGES_FILE, "w", encoding="utf-8") as f:
        json.dump(messages, f, ensure_ascii=False, indent=2)

def log_rental(log_entry):
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    logs.append(log_entry)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(logs, f, ensure_ascii=False, indent=2)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user" not in session:
            flash("로그인이 필요합니다.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ---------- 장바구니 유틸 ----------
def get_cart():
    return session.get("cart", [])

def save_cart(cart):
    session["cart"] = cart
    session.modified = True

def cart_count():
    return len(get_cart())

@app.context_processor
def inject_globals():
    # 템플릿 어디서나 cart_count 사용 가능
    return {"cart_count": cart_count()}

# ---------- 라우트 ----------
@app.route("/")
def index():
    items = load_items()
    if not isinstance(items, list):
        items = []
    return render_template("index.html", items=items, user=session.get("user"))

# 관심품목 (라디오로 카테고리 고정)
@app.route("/favorites", methods=["GET", "POST"])
def favorites():
    categories = ["패션", "생활용품", "컴퓨터", "가전", "스포츠용품", "자동차-오토바이", "산업용품"]
    if request.method == "POST":
        selected = request.form.get("category")
        if selected:
            session["fav_cat"] = selected.replace("/", "-")
        return redirect(url_for("favorites"))
    selected = session.get("fav_cat")
    items = []
    if selected:
        items = [it for it in load_items() if it.get("category") == selected]
    return render_template(
        "favorites.html",
        categories=categories,
        selected_category=selected,
        items=items,
        user=session.get("user"),
    )

# 카테고리
@app.route("/categories")
def categories():
    category_list = ["패션", "생활용품", "컴퓨터", "가전", "스포츠용품", "자동차-오토바이", "산업용품"]
    return render_template("categories.html", categories=category_list)

@app.route("/category/<name>")
def show_category(name):
    items = load_items()
    filtered = [it for it in items if it.get("category") == name]
    return render_template("item_list.html", items=filtered, title=f"{name} 카테고리", back_link="/categories")

# 물건 등록(/register는 /add로 연결)
@app.route("/register")
@login_required
def register():
    return redirect(url_for("add_item"))

@app.route("/add", methods=["GET", "POST"])
@login_required
def add_item():
    cats = ["패션", "생활용품", "컴퓨터", "가전", "스포츠용품", "자동차-오토바이", "산업용품"]
    if request.method == "POST":
        category = request.form["category"].replace("/", "-")
        new_item = {
            "name": request.form["name"],
            "description": request.form["description"],
            "daily_price": int(request.form["price"]),
            "owner": session["user"],
            "category": category,
            "is_available": True,
        }
        items = load_items()
        items.append(new_item)
        save_items(items)
        return redirect(url_for("index"))
    return render_template("add.html", categories=cats)

# ---------- 장바구니 ----------
@app.route("/cart")
@login_required
def view_cart():
    items = load_items()
    cart = get_cart()

    enriched = []
    total = 0
    for c in cart:
        idx = c.get("index")
        days = int(c.get("days", 1))
        if isinstance(idx, int) and 0 <= idx < len(items):
            it = items[idx]
            daily = int(it.get("daily_price", 0))
            subtotal = daily * days
            total += subtotal
            enriched.append({
                "index": idx,
                "name": it.get("name"),
                "description": it.get("description"),
                "daily_price": daily,
                "days": days,
                "subtotal": subtotal,
                "is_available": it.get("is_available", True),
                "owner": it.get("owner"),
                "category": it.get("category"),
            })

    return render_template("cart.html", items=enriched, total=total, user=session.get("user"))

# 장바구니 담기 (POST만)
@app.route("/cart/add/<int:index>", methods=["POST"])
@login_required
def add_to_cart(index):
    items = load_items()
    if index < 0 or index >= len(items):
        flash("존재하지 않는 물건입니다.")
        return redirect(url_for("index"))

    # days 안전 파싱
    raw = request.form.get("days", 1)
    try:
        desired_days = int(raw if raw not in ("", None) else 1)
    except ValueError:
        desired_days = 1
    if desired_days < 1:
        desired_days = 1

    cart = get_cart()
    existed = next((c for c in cart if c["index"] == index), None)
    if existed:
        existed["days"] = existed.get("days", 1) + desired_days
    else:
        cart.append({"index": index, "days": desired_days})

    save_cart(cart)
    flash("장바구니에 담았습니다.")
    return redirect(request.referrer or url_for("index"))

# 장바구니 항목 제거
@app.route("/cart/remove/<int:index>", methods=["POST"])
@login_required
def remove_from_cart(index):
    cart = [c for c in get_cart() if c.get("index") != index]
    save_cart(cart)
    flash("장바구니에서 제거했습니다.")
    return redirect(url_for("view_cart"))

# 장바구니 전체 비우기
@app.route("/cart/clear", methods=["POST"])
@login_required
def clear_cart():
    save_cart([])
    flash("장바구니를 비웠습니다.")
    return redirect(url_for("view_cart"))

# 장바구니 일수 일괄 업데이트
@app.route("/cart/update", methods=["POST"])
@login_required
def update_cart():
    cart = get_cart()
    new_cart = []
    for c in cart:
        idx = c.get("index")
        key = f"days_{idx}"
        days = request.form.get(key)
        try:
            days = int(days)
            if days < 1:
                days = 1
        except (TypeError, ValueError):
            days = c.get("days", 1)
        new_cart.append({"index": idx, "days": days})
    save_cart(new_cart)
    flash("장바구니를 업데이트했습니다.")
    return redirect(url_for("view_cart"))

# ---------- 채팅 ----------
@app.route("/chat/<int:index>", methods=["GET", "POST"])
@login_required
def chat(index):
    items = load_items()
    if not isinstance(items, list):
        items = []
    if index < 0 or index >= len(items):
        flash("존재하지 않는 물건입니다.")
        return redirect(url_for("index"))

    item = items[index]
    owner = item.get("owner")
    me = session["user"]

    messages = load_messages()
    thread = [m for m in messages if m.get("item_index") == index]

    if request.method == "POST":
        text = (request.form.get("text") or "").strip()
        if text:
            messages.append({
                "item_index": index,
                "item_name": item.get("name"),
                "owner": owner,
                "sender": me,
                "text": text,
                "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
            save_messages(messages)
        return redirect(url_for("chat", index=index))

    app.logger.info(f"[CHAT] index={index}, item={item.get('name')}, msgs={len(thread)}")
    return render_template("chat.html", item=item, index=index, owner=owner, messages=thread, me=me)

# ---------- 대여/반납/로그 ----------
@app.route("/rent/<int:index>", methods=["GET", "POST"])
@login_required
def rent_item(index):
    items = load_items()
    if index < 0 or index >= len(items):
        flash("존재하지 않는 물건입니다.")
        return redirect(url_for("index"))

    if request.method == "POST":
        if items[index].get("is_available", True):
            items[index]["is_available"] = False
            renter = session["user"]
            # days 안전 파싱
            raw = request.form.get("days", 1)
            try:
                days = int(raw if raw not in ("", None) else 1)
            except ValueError:
                days = 1
            if days < 1:
                days = 1

            save_items(items)
            log_rental({
                "item": items[index]["name"],
                "description": items[index]["description"],
                "renter": renter,
                "days": days,
                "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            })
        else:
            flash("이미 대여 중인 물건입니다.")
        return redirect(url_for("index"))
    return render_template("rent.html", index=index, item=items[index])

@app.route("/return/<int:index>")
@login_required
def return_item(index):
    items = load_items()
    if index < 0 or index >= len(items):
        flash("존재하지 않는 물건입니다.")
        return redirect(url_for("index"))
    items[index]["is_available"] = True
    save_items(items)
    return redirect(url_for("index"))

@app.route("/log")
@login_required
def view_log():
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            try:
                logs = json.load(f)
            except json.JSONDecodeError:
                logs = []
    return render_template("log.html", logs=logs)

@app.route("/my_rentals")
@login_required
def my_rentals():
    user = session["user"]
    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            try:
                all_logs = json.load(f)
            except json.JSONDecodeError:
                all_logs = []
            logs = [log for log in all_logs if log.get("renter") == user]
    return render_template("my_rentals.html", logs=logs)

@app.route("/confirm_return", methods=["POST"])
@login_required
def confirm_return():
    item_name = request.form["item_name"]
    description = request.form["description"]
    rental_date = request.form["rental_date"]
    user = session["user"]

    items = load_items()
    matched = None
    for i, it in enumerate(items):
        if it["name"] == item_name and it["description"] == description and not it["is_available"] and it["owner"] != user:
            matched = i
            break

    if matched is not None:
        items[matched]["is_available"] = True
        save_items(items)
        flash(f"✅ '{item_name}' 반납이 완료되었습니다.")
    else:
        flash("❌ 반납할 수 있는 항목을 찾지 못했습니다.")
    return redirect(url_for("my_rentals"))

# ---------- 인증 ----------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        if user_system.login(username, password):
            session["user"] = username
            flash("로그인 성공!")
            return redirect(url_for("index"))
        flash("로그인 실패. 아이디 또는 비밀번호가 틀립니다.")
    return render_template("login.html", user=session.get("user"))

@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        phone = request.form["phone"]
        if user_system.signup(username, password, phone):
            flash("회원가입 성공! 로그인 해주세요.")
            return redirect(url_for("login"))
        flash("이미 존재하는 아이디입니다.")
    return render_template("signup.html")

@app.route("/logout")
def logout():
    session.pop("user", None)
    flash("로그아웃 되었습니다.")
    return redirect(url_for("index"))

# ---------- 실행 ----------
if __name__ == "__main__":
    # 다른 기기 접속용
    app.run(host="0.0.0.0", port=5000, debug=True)
