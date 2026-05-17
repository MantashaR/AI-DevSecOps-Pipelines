@app.route("/user")
def user_route():
    name = request.args.get("name", "")
    conn = sqlite3.connect("users.db")
    cur = conn.cursor()

    # INTENTIONAL SQLI (for training)
    query = "SELECT * FROM users WHERE username = '" + name + "'"
    cur.execute(query)
    return str(cur.fetchone())


@app.route("/ping")
def ping():
    host = request.args.get("host", "127.0.0.1")

    # INTENTIONAL COMMAND INJECTION PATTERN
    result = subprocess.check_output(
        "ping -c 1 " + host,
        shell=True
    )
    return result