# test_conn.py
import os, mysql.connector

try:
    conn = mysql.connector.connect(
        host=os.environ.get("DB_HOST","localhost"),
        user=os.environ.get("DB_USER","school_user"),
        password=os.environ.get("DB_PASS","StrongP@ssw0rd"),
        database=os.environ.get("DB_NAME","school_app"),
        auth_plugin="mysql_native_password"
    )
    print("CONNECTED ✅ MySQL server version:", conn.get_server_info())
    conn.close()
except Exception as e:
    print("CONN ERROR ❌", repr(e))
